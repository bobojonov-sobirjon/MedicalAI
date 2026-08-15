from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import serializers

from .models import BodyPart, Disease, Drug, Symptom
from .utils import clean_disease_display_name, clean_display_text, description_preview


class _CleanDiseaseNameMixin:
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if "name" in data:
            data["name"] = clean_disease_display_name(data.get("name") or "")
        return data


class _CleanDrugTextMixin:
    """Unescape &reg; / &amp; in drug names and short texts for Flutter."""

    _TEXT_KEYS = (
        "name",
        "description",
        "description_preview",
        "instructions",
        "instructions_preview",
        "dosage",
    )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in self._TEXT_KEYS:
            if key in data and isinstance(data[key], str):
                data[key] = clean_display_text(data[key])
        return data


class DiseaseSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview", "created_at", "updated_at")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description)


class DiseaseSearchSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """
    Лёгкий ответ для автокомплита / полного списка пикера «История болезней».
    Flutter: List<DiseaseCatalogItem> — нужны id + name (+ description).
    """

    description = serializers.SerializerMethodField()
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description, max_chars=120)

    def get_description(self, obj: Disease) -> str:
        # Не тащим полный МКБ-текст на весь каталог — preview достаточно для пикера.
        return self.get_description_preview(obj)


class DrugMiniPublicSerializer(_CleanDrugTextMixin, serializers.ModelSerializer):
    """Краткая карточка препарата (без вложенных болезней)."""

    description_preview = serializers.SerializerMethodField()
    in_my_cabinet = serializers.SerializerMethodField()

    class Meta:
        model = Drug
        fields = (
            "id",
            "name",
            "description_preview",
            "dosage",
            "image",
            "rating",
            "in_my_cabinet",
        )

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description, max_chars=140)

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


class DiseaseMiniPublicSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """Краткая карточка болезни (без вложенных лекарств)."""

    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description, max_chars=120)


class DrugNestedInDiseaseSerializer(DrugMiniPublicSerializer):
    """Препарат внутри болезни: сразу со списком болезней (круговая навигация без лишнего GET)."""

    diseases = serializers.SerializerMethodField()
    related_diseases = serializers.SerializerMethodField()

    class Meta(DrugMiniPublicSerializer.Meta):
        fields = DrugMiniPublicSerializer.Meta.fields + (
            "diseases",
            "related_diseases",
        )

    def _disease_list(self, obj: Drug) -> list:
        cache = self.context.setdefault("_nested_drug_diseases", {})
        if obj.pk in cache:
            return cache[obj.pk]
        qs = obj.diseases.all().order_by("name")[:40]
        data = DiseaseMiniPublicSerializer(qs, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)

    def get_related_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)


class DiseaseNestedInDrugSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """Болезнь внутри лекарства: сразу со списком лекарств (круговая навигация)."""

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
        )

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(obj.description, max_chars=120)

    def _drug_list(self, obj: Disease) -> list:
        cache = self.context.setdefault("_nested_disease_drugs", {})
        if obj.pk in cache:
            return cache[obj.pk]
        try:
            qs = obj.drugs.filter(is_active=True).only(
                "id", "name", "description", "dosage", "image", "rating", "is_active"
            ).order_by("name")[:20]
            rows = list(qs)
        except Exception:
            rows = list(
                obj.drugs.all()
                .only("id", "name", "description", "dosage", "image", "rating")
                .order_by("name")[:20]
            )
        data = DrugMiniPublicSerializer(rows, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)

    def get_related_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)


class DiseaseDetailSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """Карточка заболевания + лёгкий список лекарств (без рекурсии)."""

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
        if self.context.get("skip_drugs"):
            return []
        cache = self.context.setdefault("_disease_drug_payload", {})
        if obj.pk in cache:
            return cache[obj.pk]
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "drugs" in prefetched:
            rows = sorted(prefetched["drugs"], key=lambda d: d.name)[:40]
        else:
            try:
                rows = list(
                    obj.drugs.filter(is_active=True)
                    .only("id", "name", "description", "dosage", "image", "rating")
                    .order_by("name")[:40]
                )
            except Exception:
                rows = list(obj.drugs.all().only("id", "name", "description", "dosage", "image", "rating").order_by("name")[:40])
        # Mini cards only — no nested diseases (prevents hang/timeout).
        data = DrugMiniPublicSerializer(rows, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)

    def get_related_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)


class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        fields = ("id", "name", "aliases", "created_at", "updated_at")


class BodyPartSerializer(serializers.ModelSerializer):
    class Meta:
        model = BodyPart
        fields = ("id", "code", "label", "sort_order", "created_at", "updated_at")


class DrugPickerSerializer(serializers.ModelSerializer):
    """Минимальный список для модалки «Выберите препараты» (история болезней)."""

    class Meta:
        model = Drug
        fields = ("id", "name", "dosage")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if "name" in data:
            data["name"] = clean_display_text(data.get("name") or "")
        if "dosage" in data and isinstance(data["dosage"], str):
            data["dosage"] = clean_display_text(data["dosage"])
        return data


class DrugListSerializer(_CleanDrugTextMixin, serializers.ModelSerializer):
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


class DrugSerializer(_CleanDrugTextMixin, serializers.ModelSerializer):
    """Полная карточка лекарства + болезни (у болезней сразу есть drugs для круга)."""

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
        if self.context.get("skip_related"):
            return []
        cache = self.context.setdefault("_drug_disease_payload", {})
        if obj.pk in cache:
            return cache[obj.pk]
        # Limit nested drugs per disease to keep detail response fast.
        qs = obj.diseases.only("id", "name", "description").order_by("name")[:40]
        data = DiseaseNestedInDrugSerializer(qs, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)

    def get_related_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description, max_chars=200)

    def get_instructions_preview(self, obj: Drug) -> str:
        return description_preview(obj.instructions, max_chars=200)

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
