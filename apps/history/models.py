from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.catalog.models import Disease, Drug


class DiseaseRecord(models.Model):
    """
    User private disease history entry.
    Created/edited by the user; visible only to the owner (via API).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="disease_records",
    )

    # Directory links (optional)
    disease = models.ForeignKey(
        Disease,
        verbose_name="Заболевание",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="records",
    )
    drugs = models.ManyToManyField(Drug, verbose_name="Лекарства", blank=True, related_name="records")

    # User input
    date_of_illness = models.DateField("Дата начала болезни", blank=True, null=True)
    title = models.CharField("Название (если не выбрано заболевание)", max_length=255, blank=True, default="")
    symptoms = models.TextField("Симптомы", blank=True, default="")

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Запись о болезни"
        verbose_name_plural = "Записи о болезнях"
        ordering = ["-date_of_illness", "-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "date_of_illness"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        name = self.disease.name if self.disease else self.title
        return f"{self.user_id}: {name or 'record'}"


class DoctorVisit(models.Model):
    record = models.ForeignKey(DiseaseRecord, verbose_name="Запись о болезни", on_delete=models.CASCADE, related_name="doctor_visits")

    visit_date = models.DateField("Дата посещения", blank=True, null=True)
    specialty = models.CharField("Специальность врача", max_length=255, blank=True, default="")
    doctor_full_name = models.CharField("ФИО врача", max_length=255, blank=True, default="")
    diagnosis = models.TextField("Диагноз", blank=True, default="")
    medicines_text = models.TextField("Лекарства", blank=True, default="")
    procedures_text = models.TextField("Процедуры", blank=True, default="")

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Посещение врача"
        verbose_name_plural = "Посещения врача"
        ordering = ["-visit_date", "-created_at"]
        indexes = [models.Index(fields=["record", "visit_date"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"visit:{self.record_id}:{self.visit_date or ''}"


class Analysis(models.Model):
    record = models.ForeignKey(DiseaseRecord, verbose_name="Запись о болезни", on_delete=models.CASCADE, related_name="analyses")

    taken_date = models.DateField("Дата сдачи", blank=True, null=True)
    name = models.CharField("Название анализа", max_length=255, blank=True, default="")
    result_text = models.TextField("Результат", blank=True, default="")
    photo = models.ImageField("Фото", upload_to="analyses/", blank=True, null=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Анализ"
        verbose_name_plural = "Анализы"
        ordering = ["-taken_date", "-created_at"]
        indexes = [models.Index(fields=["record", "taken_date"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"analysis:{self.record_id}:{self.name}"


class Prescription(models.Model):
    record = models.ForeignKey(DiseaseRecord, verbose_name="Запись о болезни", on_delete=models.CASCADE, related_name="prescriptions")
    photo = models.ImageField("Фото", upload_to="prescriptions/", blank=True, null=True)
    note = models.CharField("Примечание", max_length=255, blank=True, default="")

    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Рецепт"
        verbose_name_plural = "Рецепты"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["record", "created_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"prescription:{self.record_id}:{self.id}"

