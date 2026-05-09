from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        abstract = True


class Disease(TimeStampedModel):
    name = models.CharField("Название", max_length=255, unique=True)
    description = models.TextField("Описание", blank=True, default="")

    class Meta:
        verbose_name = "Заболевание"
        verbose_name_plural = "Заболевания"

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Symptom(TimeStampedModel):
    """ТЗ §7.11 — справочник симптомов для автодополнения."""

    name = models.CharField("Название", max_length=255, unique=True)
    aliases = models.CharField("Синонимы (через ;)", max_length=512, blank=True, default="")

    class Meta:
        verbose_name = "Симптом"
        verbose_name_plural = "Симптомы"
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class BodyPart(TimeStampedModel):
    """ТЗ §7.11 — части тела для UI."""

    code = models.SlugField("Код", max_length=64, unique=True)
    label = models.CharField("Название", max_length=128)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Часть тела"
        verbose_name_plural = "Части тела"
        ordering = ["sort_order", "label"]

    def __str__(self) -> str:  # pragma: no cover
        return self.label


class Drug(TimeStampedModel):
    name = models.CharField("Название", max_length=255, unique=True)
    description = models.TextField("Описание", blank=True, default="")
    dosage = models.CharField("Дозировка", max_length=255, blank=True, default="")
    image = models.ImageField("Изображение", upload_to="drugs/", blank=True, null=True)
    diseases = models.ManyToManyField(
        Disease,
        verbose_name="Можно лечить",
        blank=True,
        related_name="drugs",
        help_text="Список заболеваний, которые можно лечить этим лекарством.",
    )
    # Reserved for future user ratings; exposed in API now, default 0 until voting exists.
    rating = models.DecimalField(
        "Рейтинг",
        max_digits=4,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Средний рейтинг 0.00–5.00 (пока выставляется админом/бекендом; по умолчанию 0).",
    )

    class Meta:
        verbose_name = "Лекарство"
        verbose_name_plural = "Лекарства"

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class DrugViewLog(models.Model):
    """Последние просмотренные лекарства пользователем (ТЗ: «ранее просмотренные»)."""

    user = models.ForeignKey(
        "accounts.CustomUser",
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="drug_view_logs",
    )
    drug = models.ForeignKey(Drug, verbose_name="Лекарство", on_delete=models.CASCADE, related_name="view_logs")
    viewed_at = models.DateTimeField("Просмотрено", auto_now=True)

    class Meta:
        verbose_name = "Просмотр лекарства"
        verbose_name_plural = "Просмотры лекарств"
        constraints = [
            models.UniqueConstraint(fields=("user", "drug"), name="uniq_user_drug_view"),
        ]
        ordering = ["-viewed_at"]
        indexes = [models.Index(fields=["user", "viewed_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id}:{self.drug_id}"

