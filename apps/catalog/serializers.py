from __future__ import annotations

from rest_framework import serializers

from .models import BodyPart, Disease, Drug, Symptom
from .utils import clean_disease_display_name, description_preview


class _CleanDiseaseNameMixin:
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if "name" in data:
            data["name"] = clean_disease_display_name(data.get("name") or "")
        return data


class DiseaseSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview", "created_at", "updated_at")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description)


class DrugMiniPublicSerializer(serializers.ModelSerializer):
    """Краткая карточка препарата внутри заболевания (клик → GET /catalog/drugs/{id}/)."""

    description_preview = serializers.SerializerMethodField()
    in_my_cabinet = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = (
            "id",
            "name",
            "description",
            "description_preview",
            "instructions",
            "dosage",
            "image",
            "rating",
            "in_my_cabinet",
        )

    def get_description_preview(self, obj: Drug) -> str:
        # Клиент показывает 1–2 строки; полное описание — на экране лекарства по id.
        return description_preview(obj.description, max_chars=140)

    def get_in_my_cabinet(self, obj: Drug) -> bool:
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return False
        # Один запрос на весь вложенный список, а не запрос на каждый препарат.
        cache_key = "_cabinet_drug_ids"
        if cache_key not in self.context:
            from apps.cabinet.models import CabinetItem

            self.context[cache_key] = set(
                CabinetItem.objects.filter(user=request.user, drug_id__isnull=False)
                .values_list("drug_id", flat=True)
            )
        return obj.pk in self.context[cache_key]


class DiseaseDetailSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """Карточка заболевания + список лекарств (круговая навигация Disease ↔ Drug)."""

    description_preview = serializers.SerializerMethodField()
    drugs = serializers.SerializerMethodField()
    related_drugs = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = (
            "id",
            "name",
            "description",
            "description_preview",
            "drugs",
            "related_drugs",
            "created_at",
            "updated_at",
        )

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description)

    def _drug_list(self, obj: Disease) -> list:
        cache = self.context.setdefault("_disease_drug_payload", {})
        if obj.pk in cache:
            return cache[obj.pk]
        qs = obj.drugs.filter(is_active=True).order_by("name")[:80]
        data = DrugMiniPublicSerializer(qs, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)

    def get_related_drugs(self, obj: Disease) -> list:
        # Alias для клиента («Лекарства» / круговая навигация).
        return self._drug_list(obj)


class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        fields = ("id", "name", "aliases", "created_at", "updated_at")


class BodyPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = BodyPart
        fields = ("id", "code", "label", "sort_order", "created_at", "updated_at")


class DiseaseMiniPublicSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """Краткая карточка болезни внутри лекарства (клик → GET /catalog/diseases/{id}/)."""

    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description, max_chars=120)


class DrugListSerializer(serializers.ModelSerializer):
    """Лёгкая карточка для списка лекарств (без вложенных diseases — они в detail)."""

    description_preview = serializers.SerializerMethodField()
    instructions_preview = serializers.SerializerMethodField()
    diseases_count = serializers.IntegerField(read_only=True)
    in_my_cabinet = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = (
            "id",
            "name",
            "description_preview",
            "instructions_preview",
            "dosage",
            "image",
            "rating",
            "diseases_count",
            "in_my_cabinet",
            "created_at",
            "updated_at",
        )

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description, max_chars=160)

    def get_instructions_preview(self, obj: Drug) -> str:
        return description_preview(obj.instructions, max_chars=120)

    def get_in_my_cabinet(self, obj: Drug) -> bool:
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return False
        cache_key = "_cabinet_drug_ids"
        if cache_key not in self.context:
            from apps.cabinet.models import CabinetItem

            self.context[cache_key] = set(
                CabinetItem.objects.filter(user=request.user, drug_id__isnull=False)
                .values_list("drug_id", flat=True)
            )
        return obj.pk in self.context[cache_key]


class DrugSerializer(serializers.ModelSerializer):
    """Полная карточка лекарства + связанные болезни (круговая навигация)."""

    diseases = serializers.SerializerMethodField()
    related_diseases = serializers.SerializerMethodField()
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
            "related_diseases",
            "in_my_cabinet",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "rating": {"help_text": "Средний рейтинг 0–5 (пока только для чтения; по умолчанию 0)."},
        }

    def _disease_list(self, obj: Drug) -> list:
        cache = self.context.setdefault("_drug_disease_payload", {})
        if obj.pk in cache:
            return cache[obj.pk]
        qs = obj.diseases.all().order_by("name")[:60]
        data = DiseaseMiniPublicSerializer(qs, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)

    def get_related_diseases(self, obj: Drug) -> list:
        # Alias для клиента («Связанные заболевания»).
        return self._disease_list(obj)

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description, max_chars=200)

    def get_instructions_preview(self, obj: Drug) -> str:
        return description_preview(obj.instructions, max_chars=200)

    def get_in_my_cabinet(self, obj: Drug) -> bool:
        request = self.context.get("request")
        if not request or not getattr(request.user, "is_authenticated", False):
            return False
        from apps.cabinet.models import CabinetItem

        return CabinetItem.objects.filter(user=request.user, drug_id=obj.pk).exists()

