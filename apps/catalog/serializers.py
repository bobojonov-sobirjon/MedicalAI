from __future__ import annotations

from rest_framework import serializers

from .models import Disease, Drug


class DiseaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disease
        fields = ("id", "name", "description", "created_at", "updated_at")


class DrugSerializer(serializers.ModelSerializer):
    diseases = DiseaseSerializer(read_only=True, many=True)

    class Meta:
        model = Drug
        fields = ("id", "name", "description", "dosage", "image", "rating", "diseases", "created_at", "updated_at")
        extra_kwargs = {
            "rating": {"help_text": "Средний рейтинг 0–5 (пока только для чтения; по умолчанию 0)."},
        }

