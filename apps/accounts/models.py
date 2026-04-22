from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    Minimal, extensible user model for mobile auth.
    We keep username for compatibility, but treat email/phone as primary identifiers.
    """

    class Gender(models.TextChoices):
        MALE = "male", "Мужской"
        FEMALE = "female", "Женский"
        OTHER = "other", "Другое"

    email = models.EmailField("Email", blank=True, null=True, unique=True)
    phone_number = models.CharField("Телефон", max_length=32, blank=True, null=True, unique=True)
    avatar = models.ImageField("Аватар", upload_to="avatars/", blank=True, null=True)

    nickname = models.CharField("Ник", max_length=64, blank=True, default="", help_text="Латиница и цифры.")
    gender = models.CharField("Пол", max_length=16, choices=Gender.choices, blank=True, default="")
    city = models.CharField("Город", max_length=128, blank=True, default="", help_text="Справочник или произвольно.")
    date_of_birth = models.DateField("Дата рождения", blank=True, null=True)
    height_cm = models.PositiveSmallIntegerField("Рост (см)", blank=True, null=True)
    weight_kg = models.DecimalField("Вес (кг)", max_digits=5, decimal_places=2, blank=True, null=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self) -> str:  # pragma: no cover
        return self.get_full_name() or self.email or self.phone_number or self.username


class PasswordResetCode(models.Model):
    """TZ §7.5: one-time email code for forgot-password flow."""

    user = models.ForeignKey(CustomUser, verbose_name="Пользователь", on_delete=models.CASCADE, related_name="password_reset_codes")
    code_hash = models.CharField("Хэш кода", max_length=128)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    expires_at = models.DateTimeField("Истекает")
    used = models.BooleanField("Использован", default=False)

    class Meta:
        verbose_name = "Код сброса пароля"
        verbose_name_plural = "Коды сброса пароля"
        indexes = [
            models.Index(fields=["user", "used", "expires_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"reset#{self.pk} user={self.user_id}"


class SocialAccount(models.Model):
    class Provider(models.TextChoices):
        VK = "vk", "VK"
        GOOGLE = "google", "Google"
        APPLE = "apple", "Apple"

    user = models.ForeignKey(CustomUser, verbose_name="Пользователь", on_delete=models.CASCADE, related_name="social_accounts")
    provider = models.CharField("Провайдер", max_length=16, choices=Provider.choices)
    provider_user_id = models.CharField("ID пользователя у провайдера", max_length=255)

    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Социальный аккаунт"
        verbose_name_plural = "Социальные аккаунты"
        unique_together = (("provider", "provider_user_id"),)
        indexes = [
            models.Index(fields=["provider", "provider_user_id"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.provider}:{self.provider_user_id}"

