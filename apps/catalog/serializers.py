from __future__ import annotations

from rest_framework import serializers

from .models import BodyPart, Disease, Drug, Symptom
from .utils import description_preview


class DiseaseSerializer(serializers.ModelSerializer):
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview", "created_at", "updated_at")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description)


class DrugMiniPublicSerializer(serializers.ModelSerializer):
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = ("id", "name", "description", "description_preview", "dosage", "image", "rating")

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description)


class DiseaseDetailSerializer(serializers.ModelSerializer):
    """TZ §7.9 — карточка заболевания с блоком лекарств."""

    description_preview = serializers.SerializerMethodField()
    drugs = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview", "drugs", "created_at", "updated_at")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description)

    def get_drugs(self, obj: Disease) -> list:
        qs = obj.drugs.all().order_by("name")[:80]
        return DrugMiniPublicSerializer(qs, many=True, context=self.context).data


class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        fields = ("id", "name", "aliases", "created_at", "updated_at")


class BodyPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = BodyPart
        fields = ("id", "code", "label", "sort_order", "created_at", "updated_at")


class DrugSerializer(serializers.ModelSerializer):
    diseases = DiseaseSerializer(read_only=True, many=True)
    in_my_cabinet = serializers.SerializerMethodField()
    description_preview = serializers.SerializerMethodField()
    instructions_preview = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = (
            "id",
            "name",
            "description",
            "description_preview",
            "instructions",
            "instructions_preview",
            "dosage",
            "image",
            "rating",
            "diseases",
            "in_my_cabinet",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "rating": {"help_text": "Средний рейтинг 0–5 (пока только для чтения; по умолчанию 0)."},
        }

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description)

    def get_instructions_preview(self, obj: Drug) -> str:
        return description_preview(obj.instructions, max_chars=360)

    def get_in_my_cabinet(self, obj: Drug) -> bool:
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return False
        from apps.cabinet.models import CabinetItem

        return CabinetItem.objects.filter(user=request.user, drug_id=obj.pk).exists()

