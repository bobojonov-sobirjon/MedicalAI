from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.catalog.models import Drug


class CabinetItem(models.Model):
    """Моя аптечка пользователя."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="cabinet_items",
    )
    drug = models.ForeignKey(
        Drug,
        verbose_name="Лекарство из справочника",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cabinet_entries",
    )
    custom_name = models.CharField("Название (если не из справочника)", max_length=255, blank=True, default="")
    expires_at = models.DateField("Годен до", blank=True, null=True)
    note = models.TextField("Заметка", blank=True, default="")
    photo = models.ImageField("Фото упаковки", upload_to="cabinet/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Запись аптечки"
        verbose_name_plural = "Аптечка"
        ordering = ["-expires_at", "-created_at"]
        indexes = [models.Index(fields=["user", "expires_at"])]

    def display_name(self) -> str:
        if self.drug_id:
            return self.drug.name
        return self.custom_name or "—"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id}: {self.display_name()}"
