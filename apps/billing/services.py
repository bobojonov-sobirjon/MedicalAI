from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.medic.models import NotificationEvent
from apps.medic.ws_broadcast import broadcast_notification_event

from .models import Payment, TariffPlan, UserBillingProfile, UserSubscription
from .robokassa import build_payment_url, format_out_sum, robokassa_configured, verify_result_signature, verify_success_signature

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
    now = timezone.now()
    qs = (
        UserSubscription.objects.filter(user=user, status=UserSubscription.Status.ACTIVE)
        .select_related("tariff")
        .order_by("-started_at")
    )
    for sub in qs:
        if sub.expires_at and sub.expires_at <= now:
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


def _expires_at_for_tariff(tariff: TariffPlan, started_at=None):
    started_at = started_at or timezone.now()
    if tariff.is_auto_trial:
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
    Один раз на аккаунт: пробный тариф при первой регистрации (ТЗ §8.2.4).
    """
    profile = get_or_create_billing_profile(user)
    if profile.free_trial_used:
        return get_active_subscription(user)

    trial = TariffPlan.objects.filter(is_auto_trial=True, is_active=True).order_by("sort_order").first()
    if not trial:
        trial = TariffPlan.objects.filter(slug="free_trial", is_active=True).first()
    if not trial:
        logger.warning("No auto-trial tariff configured; skipping welcome trial for user %s", user.pk)
        return None

    profile.free_trial_used = True
    profile.save(update_fields=["free_trial_used", "updated_at"])

    sub = _activate_subscription(user, trial, source=UserSubscription.Source.AUTO_TRIAL)
    logger.info("Granted welcome trial to user %s until %s", user.pk, sub.expires_at)
    return sub


@transaction.atomic
def assign_free_plan(user) -> UserSubscription:
    free = TariffPlan.objects.filter(slug="free", is_active=True).first()
    if not free:
        raise ValueError("Tariff 'free' is not configured")
    return _activate_subscription(user, free, source=UserSubscription.Source.AUTO_FREE)


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

    payment = Payment.objects.select_for_update().select_related("tariff", "user").get(robokassa_inv_id=inv_id)
    expected = format_out_sum(Decimal(payment.amount_rub))
    if format_out_sum(Decimal(out_sum)) != expected:
        payment.status = Payment.Status.FAILED
        payment.error_message = f"Сумма не совпадает: {out_sum} != {expected}"
        payment.callback_payload = payload
        payment.save(update_fields=["status", "error_message", "callback_payload", "updated_at"])
        _log_payment_error(payment.error_message, user=payment.user, path=source_path)
        raise ValueError("Сумма не совпадает")

    if payment.status == Payment.Status.PAID:
        return payment

    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.callback_payload = payload
    payment.save(update_fields=["status", "paid_at", "callback_payload", "updated_at"])

    _activate_subscription(
        payment.user,
        payment.tariff,
        source=UserSubscription.Source.PAYMENT,
        payment=payment,
    )
    _notify_payment_success(payment)
    return payment


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
    sub = get_active_subscription(user)
    profile = get_or_create_billing_profile(user)
    access_scope = get_access_scope(user)
    paywall = get_paywall_payload() if access_scope != "full" else None
    if sub is None:
        return {
            "has_active_subscription": False,
            "free_trial_used": profile.free_trial_used,
            "can_get_free_trial": False,
            "access_scope": access_scope,
            "allowed_sections": ["history"],
            "tariff": None,
            "limits": get_user_limits(user),
            "paywall": paywall,
        }
    days_left = None
    if sub.expires_at:
        delta = sub.expires_at - timezone.now()
        days_left = max(0, delta.days)
    return {
        "has_active_subscription": True,
        "free_trial_used": profile.free_trial_used,
        "can_get_free_trial": not profile.free_trial_used,
        "access_scope": access_scope,
        "allowed_sections": ["history"] if access_scope == "history_only" else ["all"],
        "tariff": {
            "slug": sub.tariff.slug,
            "tier": sub.tariff.tier,
            "title": sub.tariff.title,
            "description": sub.tariff.description,
            "price_rub": str(sub.tariff.price_rub),
            "expires_at": sub.expires_at,
            "days_left": days_left,
            "source": sub.source,
        },
        "limits": get_user_limits(user),
        "paywall": paywall,
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

        if not sub.tariff.is_auto_trial:
            continue

        days_left = (sub.expires_at.date() - now.date()).days
        sent = set(sub.expiry_warnings_sent or [])
        for threshold in warning_days:
            if days_left <= threshold and threshold not in sent:
                _notify_trial_expiring(sub, days_left if days_left > 0 else 1)
                sent.add(threshold)
        if sent != set(sub.expiry_warnings_sent or []):
            sub.expiry_warnings_sent = sorted(sent)
            sub.save(update_fields=["expiry_warnings_sent"])
