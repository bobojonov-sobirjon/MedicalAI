from __future__ import annotations

import logging
import math
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.medic.models import NotificationEvent
from apps.medic.ws_broadcast import broadcast_notification_event

from .models import Payment, TariffPlan, UserBillingProfile, UserSubscription
from .robokassa import (
    build_payment_url,
    format_out_sum,
    robokassa_configured,
    verify_result_signature,
    verify_success_signature,
)

logger = logging.getLogger(__name__)


def _trial_days() -> int:
    trial_days = getattr(settings, "FREE_TRIAL_DAYS", None)
    if trial_days is not None:
        return max(1, int(trial_days))
    months = int(getattr(settings, "FREE_TRIAL_MONTHS", 3))
    return max(1, months * 30)


def _warning_days() -> list[int]:
    raw = getattr(settings, "SUBSCRIPTION_EXPIRY_WARNING_DAYS", "7,3,1")
    if isinstance(raw, str):
        return sorted({int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}, reverse=True)
    return [7, 3, 1]


def get_or_create_billing_profile(user) -> UserBillingProfile:
    profile, _ = UserBillingProfile.objects.get_or_create(user=user)
    return profile


def get_active_subscription(user) -> UserSubscription | None:
    """Return current non-expired ACTIVE subscription; expire stale rows lazily."""
    now = timezone.now()
    qs = (
        UserSubscription.objects.filter(user=user, status=UserSubscription.Status.ACTIVE)
        .select_related("tariff")
        .order_by("-started_at")
    )
    for sub in qs:
        if sub.expires_at and sub.expires_at <= now:
            sub.status = UserSubscription.Status.EXPIRED
            sub.save(update_fields=["status"])
            continue
        return sub
    return None


def get_access_scope(user) -> str:
    sub = get_active_subscription(user)
    if sub and sub.tariff.tier in {
        TariffPlan.Tier.FREE_TRIAL,
        TariffPlan.Tier.STANDARD,
        TariffPlan.Tier.PREMIUM,
    }:
        return "full"
    return "history_only"


def get_paywall_payload() -> dict:
    return {
        "title": "Бесплатный период закончился",
        "message": "Бесплатный период закончился. Оплатить подписку.",
        "cta_text": "Оплатить подписку",
        "cta_action": "open_subscription_payment",
    }


def get_user_limits(user) -> dict:
    sub = get_active_subscription(user)
    if sub and sub.tariff.limits:
        return dict(sub.tariff.limits)
    free = TariffPlan.objects.filter(slug="free", is_active=True).first()
    if free and free.limits:
        return dict(free.limits)
    return {}


def _ensure_default_trial_tariff() -> TariffPlan:
    trial = TariffPlan.objects.filter(is_auto_trial=True, is_active=True).order_by("sort_order").first()
    if trial:
        return trial
    trial = TariffPlan.objects.filter(slug="free_trial").first()
    if trial:
        trial.is_active = True
        trial.is_auto_trial = True
        trial.tier = TariffPlan.Tier.FREE_TRIAL
        trial.validity_days = _trial_days()
        trial.is_purchasable = False
        trial.save(
            update_fields=[
                "is_active",
                "is_auto_trial",
                "tier",
                "validity_days",
                "is_purchasable",
            ]
        )
        return trial
    return TariffPlan.objects.create(
        slug="free_trial",
        tier=TariffPlan.Tier.FREE_TRIAL,
        title="Пробный период",
        description="Бесплатный доступ 24 часа при регистрации. Выдаётся один раз.",
        price_rub=0,
        validity_days=_trial_days(),
        sort_order=0,
        is_purchasable=False,
        is_auto_trial=True,
        is_active=True,
        limits={
            "max_disease_records": None,
            "max_cabinet_items": None,
            "extended_ai": True,
            "calendar_ai": True,
            "useful_tips": True,
        },
    )


def _ensure_default_free_tariff() -> TariffPlan:
    free = TariffPlan.objects.filter(slug="free", is_active=True).first()
    if free:
        return free
    free = TariffPlan.objects.filter(slug="free").first()
    if free:
        free.is_active = True
        free.tier = TariffPlan.Tier.FREE
        free.is_purchasable = False
        free.is_auto_trial = False
        free.validity_days = None
        free.description = "После окончания пробного периода доступен только раздел истории болезни."
        free.limits = {
            "max_disease_records": None,
            "max_cabinet_items": 0,
            "extended_ai": False,
            "calendar_ai": False,
            "useful_tips": False,
        }
        free.save()
        return free
    return TariffPlan.objects.create(
        slug="free",
        tier=TariffPlan.Tier.FREE,
        title="Бесплатный",
        description="После окончания пробного периода доступен только раздел истории болезни.",
        price_rub=0,
        validity_days=None,
        sort_order=1,
        is_purchasable=False,
        is_auto_trial=False,
        is_active=True,
        limits={
            "max_disease_records": None,
            "max_cabinet_items": 0,
            "extended_ai": False,
            "calendar_ai": False,
            "useful_tips": False,
        },
    )


def _expires_at_for_tariff(tariff: TariffPlan, started_at=None):
    started_at = started_at or timezone.now()
    if tariff.is_auto_trial or tariff.tier == TariffPlan.Tier.FREE_TRIAL:
        return started_at + timedelta(days=_trial_days())
    if tariff.validity_days:
        return started_at + timedelta(days=int(tariff.validity_days))
    return None


@transaction.atomic
def _activate_subscription(
    user,
    tariff: TariffPlan,
    *,
    source: str,
    payment: Payment | None = None,
    started_at=None,
) -> UserSubscription:
    started_at = started_at or timezone.now()
    UserSubscription.objects.filter(user=user, status=UserSubscription.Status.ACTIVE).update(
        status=UserSubscription.Status.SUPERSEDED
    )
    return UserSubscription.objects.create(
        user=user,
        tariff=tariff,
        status=UserSubscription.Status.ACTIVE,
        source=source,
        started_at=started_at,
        expires_at=_expires_at_for_tariff(tariff, started_at),
        payment=payment,
    )


@transaction.atomic
def grant_welcome_trial(user) -> UserSubscription | None:
    """
    Один раз на аккаунт: пробный тариф 24 часа при первой регистрации.
    """
    profile = get_or_create_billing_profile(user)
    if profile.free_trial_used:
        return get_active_subscription(user)

    trial = _ensure_default_trial_tariff()
    profile.free_trial_used = True
    profile.save(update_fields=["free_trial_used", "updated_at"])

    sub = _activate_subscription(user, trial, source=UserSubscription.Source.AUTO_TRIAL)
    logger.info("Granted welcome trial to user %s until %s", user.pk, sub.expires_at)
    return sub


@transaction.atomic
def assign_free_plan(user) -> UserSubscription:
    free = _ensure_default_free_tariff()
    return _activate_subscription(user, free, source=UserSubscription.Source.AUTO_FREE)


@transaction.atomic
def ensure_user_subscription(user) -> UserSubscription | None:
    """
    Guarantee a billing state for the user:
    - active paid/trial → keep
    - no trial used → grant 24h trial
    - otherwise → free (history_only)
    """
    sub = get_active_subscription(user)
    if sub:
        return sub

    profile = get_or_create_billing_profile(user)
    if not profile.free_trial_used:
        return grant_welcome_trial(user)

    try:
        return assign_free_plan(user)
    except Exception:
        logger.exception("Failed to assign free plan for user %s", user.pk)
        return None


@transaction.atomic
def create_payment_for_tariff(user, tariff_slug: str) -> tuple[Payment, str]:
    tariff = TariffPlan.objects.get(slug=tariff_slug, is_active=True, is_purchasable=True)
    if tariff.price_rub <= 0:
        raise ValueError("Этот тариф нельзя оплатить")

    if not robokassa_configured():
        raise ValueError("Robokassa не настроена на сервере")

    payment = Payment.objects.create(
        user=user,
        tariff=tariff,
        amount_rub=tariff.price_rub,
        status=Payment.Status.PENDING,
        description=f"MedicAi - {tariff.title}",
    )
    payment.robokassa_inv_id = payment.pk
    payment.save(update_fields=["robokassa_inv_id"])

    url = build_payment_url(
        inv_id=payment.robokassa_inv_id,
        amount=Decimal(payment.amount_rub),
        description=payment.description,
    )
    return payment, url


def _amounts_equal(out_sum: str, expected: Decimal) -> bool:
    """Robokassa may send 399 / 399.0 / 399.00 — compare as Decimal."""
    try:
        got = Decimal(str(out_sum).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError):
        return False
    return got.quantize(Decimal("0.01")) == Decimal(expected).quantize(Decimal("0.01"))


@transaction.atomic
def _complete_payment_if_valid(
    *,
    out_sum: str,
    inv_id: int,
    signature_value: str,
    payload: dict,
    signature_ok: bool,
    source_path: str,
) -> Payment:
    if not signature_ok:
        _log_payment_error(f"Invalid Robokassa signature for InvId={inv_id}", path=source_path)
        raise ValueError("Неверная подпись")

    payment = (
        Payment.objects.select_for_update()
        .select_related("tariff", "user")
        .filter(robokassa_inv_id=inv_id)
        .first()
    )
    if payment is None:
        payment = (
            Payment.objects.select_for_update()
            .select_related("tariff", "user")
            .filter(pk=inv_id)
            .first()
        )
    if payment is None:
        _log_payment_error(f"Payment not found for InvId={inv_id}", path=source_path)
        raise Payment.DoesNotExist(f"InvId={inv_id}")

    if not _amounts_equal(out_sum, Decimal(payment.amount_rub)):
        payment.status = Payment.Status.FAILED
        payment.error_message = f"Сумма не совпадает: {out_sum} != {format_out_sum(Decimal(payment.amount_rub))}"
        payment.callback_payload = payload
        payment.save(update_fields=["status", "error_message", "callback_payload", "updated_at"])
        _log_payment_error(payment.error_message, user=payment.user, path=source_path)
        raise ValueError("Сумма не совпадает")

    if payment.status == Payment.Status.PAID:
        # Idempotent: ensure paid subscription still active (webhook may retry).
        ensure_paid_subscription(payment)
        return payment

    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.callback_payload = payload
    if payment.robokassa_inv_id is None:
        payment.robokassa_inv_id = inv_id
    payment.save(
        update_fields=["status", "paid_at", "callback_payload", "robokassa_inv_id", "updated_at"]
    )

    ensure_paid_subscription(payment)
    _notify_payment_success(payment)
    logger.info(
        "Payment #%s (InvId=%s) marked PAID; user=%s tariff=%s",
        payment.pk,
        inv_id,
        payment.user_id,
        payment.tariff.slug,
    )
    return payment


def ensure_paid_subscription(payment: Payment) -> UserSubscription:
    """Activate/refresh paid subscription for a confirmed payment."""
    active = get_active_subscription(payment.user)
    if (
        active
        and active.payment_id == payment.pk
        and active.tariff_id == payment.tariff_id
        and active.source == UserSubscription.Source.PAYMENT
    ):
        return active
    return _activate_subscription(
        payment.user,
        payment.tariff,
        source=UserSubscription.Source.PAYMENT,
        payment=payment,
    )


@transaction.atomic
def process_robokassa_result(*, out_sum: str, inv_id: int, signature_value: str, payload: dict) -> Payment:
    return _complete_payment_if_valid(
        out_sum=out_sum,
        inv_id=inv_id,
        signature_value=signature_value,
        payload=payload,
        signature_ok=verify_result_signature(out_sum=out_sum, inv_id=inv_id, signature_value=signature_value),
        source_path="/api/billing/robokassa/result/",
    )


@transaction.atomic
def process_robokassa_success(*, out_sum: str, inv_id: int, signature_value: str, payload: dict) -> Payment:
    """Fallback: подтверждение по Success URL (Password1), если Result URL недоступен."""
    return _complete_payment_if_valid(
        out_sum=out_sum,
        inv_id=inv_id,
        signature_value=signature_value,
        payload=payload,
        signature_ok=verify_success_signature(out_sum=out_sum, inv_id=inv_id, signature_value=signature_value),
        source_path="/api/billing/robokassa/success/",
    )


def _log_payment_error(message: str, user=None, path: str = "/api/billing/robokassa/result/") -> None:
    logger.error("Payment error: %s", message)
    try:
        from apps.medic.models import ApiErrorLog

        ApiErrorLog.objects.create(
            status_code=402,
            message=message[:4000],
            path=path,
            user=user,
        )
    except Exception:
        pass


def _notify_payment_success(payment: Payment) -> None:
    event = NotificationEvent.objects.create(
        recipient=payment.user,
        kind=NotificationEvent.Kind.SYSTEM,
        title="Подписка активирована",
        body=f"Тариф «{payment.tariff.title}» успешно подключён.",
        meta={"billing": "subscription_activated", "tariff": payment.tariff.slug},
    )
    broadcast_notification_event(event, created=True)


def _notify_trial_expiring(sub: UserSubscription, days_left: int) -> None:
    title = "Пробный период заканчивается"
    if days_left <= 1:
        body = "Завтра заканчивается бесплатный период. Выберите тариф Standard или Premium."
    else:
        body = f"Через {days_left} дн. заканчивается бесплатный период. Выберите тариф Standard или Premium."
    event = NotificationEvent.objects.create(
        recipient=sub.user,
        kind=NotificationEvent.Kind.SYSTEM,
        title=title,
        body=body,
        meta={
            "billing": "trial_expiring",
            "days_left": days_left,
            "tariff": sub.tariff.slug,
            "link": "medicai://subscription",
        },
    )
    broadcast_notification_event(event, created=True)


def subscription_status_payload(user) -> dict:
    ensure_user_subscription(user)
    sub = get_active_subscription(user)
    profile = get_or_create_billing_profile(user)
    access_scope = get_access_scope(user)
    paywall = get_paywall_payload() if access_scope != "full" else None

    is_trial_active = bool(
        sub
        and sub.tariff.tier == TariffPlan.Tier.FREE_TRIAL
        and access_scope == "full"
    )
    is_paid_active = bool(
        sub
        and sub.tariff.tier in {TariffPlan.Tier.STANDARD, TariffPlan.Tier.PREMIUM}
        and access_scope == "full"
    )
    requires_payment = access_scope != "full"

    base = {
        "has_active_subscription": bool(sub and access_scope == "full"),
        "is_trial_active": is_trial_active,
        "is_paid_active": is_paid_active,
        "requires_payment": requires_payment,
        "free_trial_used": profile.free_trial_used,
        "can_get_free_trial": not profile.free_trial_used,
        "access_scope": access_scope,
        "allowed_sections": ["history"] if access_scope == "history_only" else ["all"],
        "limits": get_user_limits(user),
        "paywall": paywall,
        "trial_days": _trial_days(),
    }

    if sub is None:
        return {
            **base,
            "tariff": None,
            "seconds_left": None,
            "hours_left": None,
            "days_left": None,
        }

    seconds_left = None
    hours_left = None
    days_left = None
    if sub.expires_at:
        seconds_left = max(0, int((sub.expires_at - timezone.now()).total_seconds()))
        hours_left = max(0, math.ceil(seconds_left / 3600)) if seconds_left else 0
        # Ceil days so 24h trial shows days_left=1 until the last second of day 1 window.
        days_left = max(0, math.ceil(seconds_left / 86400)) if seconds_left else 0

    return {
        **base,
        "tariff": {
            "slug": sub.tariff.slug,
            "tier": sub.tariff.tier,
            "title": sub.tariff.title,
            "description": sub.tariff.description,
            "price_rub": str(sub.tariff.price_rub),
            "started_at": sub.started_at,
            "expires_at": sub.expires_at,
            "seconds_left": seconds_left,
            "hours_left": hours_left,
            "days_left": days_left,
            "source": sub.source,
            "is_trial": sub.tariff.tier == TariffPlan.Tier.FREE_TRIAL,
            "is_paid": sub.tariff.tier in {TariffPlan.Tier.STANDARD, TariffPlan.Tier.PREMIUM},
        },
        "seconds_left": seconds_left,
        "hours_left": hours_left,
        "days_left": days_left,
    }


def process_subscription_lifecycle_tick() -> None:
    """Истечение подписок, переход на Free, напоминания (push через NotificationEvent + WS)."""
    now = timezone.now()
    warning_days = _warning_days()

    active = UserSubscription.objects.filter(status=UserSubscription.Status.ACTIVE).select_related(
        "tariff", "user"
    )
    for sub in active:
        if not sub.expires_at:
            continue

        if sub.expires_at <= now:
            sub.status = UserSubscription.Status.EXPIRED
            sub.save(update_fields=["status"])
            try:
                assign_free_plan(sub.user)
            except ValueError:
                logger.warning("Cannot assign free plan after expiry for user %s", sub.user_id)
            expired_event = NotificationEvent.objects.create(
                recipient=sub.user,
                kind=NotificationEvent.Kind.SYSTEM,
                title="Подписка завершена",
                body="Срок действия тарифа истёк. Доступен бесплатный тариф — подключите Standard или Premium.",
                meta={"billing": "subscription_expired"},
            )
            broadcast_notification_event(expired_event, created=True)
            continue

        if not sub.tariff.is_auto_trial and sub.tariff.tier != TariffPlan.Tier.FREE_TRIAL:
            continue

        days_left = max(0, math.ceil((sub.expires_at - now).total_seconds() / 86400))
        sent = set(sub.expiry_warnings_sent or [])
        for threshold in warning_days:
            if days_left <= threshold and threshold not in sent:
                _notify_trial_expiring(sub, days_left if days_left > 0 else 1)
                sent.add(threshold)
        if sent != set(sub.expiry_warnings_sent or []):
            sub.expiry_warnings_sent = sorted(sent)
            sub.save(update_fields=["expiry_warnings_sent"])
