from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class TariffPlan(models.Model):
    """Тариф: название, описание, цена, срок действия и лимиты (ТЗ §4.2, §8.2.4, доп. §9.4)."""

    class Tier(models.TextChoices):
        FREE_TRIAL = "free_trial", "Пробный период"
        FREE = "free", "Бесплатный"
        STANDARD = "standard", "Стандарт"
        PREMIUM = "premium", "Премиум"

    slug = models.SlugField("Код", max_length=32, unique=True)
    tier = models.CharField("Уровень", max_length=16, choices=Tier.choices)
    title = models.CharField("Название", max_length=128)
    description = models.TextField("Описание", blank=True, default="")
    price_rub = models.DecimalField("Цена (₽)", max_digits=10, decimal_places=2, default=0)
    validity_days = models.PositiveIntegerField(
        "Срок действия (дней)",
        null=True,
        blank=True,
        help_text="Пусто — без срока (бессрочно).",
    )
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активен", default=True)
    is_purchasable = models.BooleanField("Можно купить", default=True)
    is_auto_trial = models.BooleanField(
        "Выдаётся при регистрации",
        default=False,
        help_text="Один раз на аккаунт; повторно не выдаётся.",
    )
    limits = models.JSONField(
        "Лимиты и возможности",
        default=dict,
        blank=True,
        help_text="max_disease_records, max_cabinet_items, extended_ai, calendar_ai, …",
    )

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:  # pragma: no cover
        return self.title


class UserBillingProfile(models.Model):
    """Один бесплатный trial на аккаунт (ТЗ §8.2.4)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="billing_profile",
    )
    free_trial_used = models.BooleanField("Пробный период использован", default=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Биллинг-профиль"
        verbose_name_plural = "Биллинг-профили"

    def __str__(self) -> str:  # pragma: no cover
        return f"billing#{self.user_id}"


class UserSubscription(models.Model):
    """Активная или архивная подписка пользователя на тариф."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        EXPIRED = "expired", "Истекла"
        SUPERSEDED = "superseded", "Заменена"

    class Source(models.TextChoices):
        AUTO_TRIAL = "auto_trial", "Авто trial"
        AUTO_FREE = "auto_free", "Авто Free"
        PAYMENT = "payment", "Оплата"
        ADMIN = "admin", "Админ"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    tariff = models.ForeignKey(
        TariffPlan,
        verbose_name="Тариф",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.ACTIVE)
    source = models.CharField("Источник", max_length=16, choices=Source.choices)
    started_at = models.DateTimeField("Начало", default=timezone.now)
    expires_at = models.DateTimeField("Окончание", null=True, blank=True)
    payment = models.ForeignKey(
        "Payment",
        verbose_name="Платёж",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subscriptions",
    )
    expiry_warnings_sent = models.JSONField(
        "Отправленные напоминания (дней до конца)",
        default=list,
        blank=True,
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Подписка пользователя"
        verbose_name_plural = "Подписки пользователей"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "status", "-expires_at"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"sub#{self.pk} user={self.user_id} {self.tariff.slug}"

    @property
    def is_active_now(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True


class Payment(models.Model):
    """Платёж через Robokassa (ТЗ §4.2, §3.9 — логирование)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        PAID = "paid", "Оплачен"
        FAILED = "failed", "Ошибка"
        CANCELLED = "cancelled", "Отменён"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    tariff = models.ForeignKey(
        TariffPlan,
        verbose_name="Тариф",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount_rub = models.DecimalField("Сумма (₽)", max_digits=10, decimal_places=2)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.PENDING)
    robokassa_inv_id = models.PositiveBigIntegerField("InvId Robokassa", unique=True, null=True, blank=True)
    description = models.CharField("Описание", max_length=512, blank=True, default="")
    paid_at = models.DateTimeField("Оплачено", null=True, blank=True)
    callback_payload = models.JSONField("Данные callback", default=dict, blank=True)
    error_message = models.TextField("Ошибка", blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"pay#{self.pk} {self.amount_rub}₽ {self.status}"
