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

