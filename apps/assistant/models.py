from __future__ import annotations

from django.conf import settings
from django.db import models


class AssistantDiagnosis(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="assistant_diagnoses",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Для кого диагностика",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_diagnoses_as_subject",
        help_text="Член семьи или сам владелец (ТЗ §8.2.3).",
    )

    symptom_ids = models.JSONField("ID симптомов", default=list)
    symptoms_text = models.TextField("Доп. симптомы (текст)", blank=True, default="")
    body_part_ids = models.JSONField("ID частей тела", default=list)
    temperature_c = models.FloatField("Температура (°C)", null=True, blank=True)
    blood_pressure = models.CharField("Давление", max_length=32, blank=True, default="")

    result = models.JSONField("Результат (JSON)")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Диагноз помощника"
        verbose_name_plural = "Диагнозы помощника"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

