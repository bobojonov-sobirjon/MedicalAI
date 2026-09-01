from __future__ import annotations

from django.db.models import Prefetch
from rest_framework import serializers

from .models import BodyPart, Disease, Drug, Symptom
from .utils import (
    clean_disease_display_name,
    clean_display_text,
    clean_drug_plain_text,
    description_preview,
    disease_card_text,
    flatten_display_text,
    format_section_markdown,
    is_registry_meta_text,
    strip_markdown_bold_for_plain,
    strip_mkb_public_text,
)


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
                if key == "name" or key.endswith("_preview") or key == "dosage":
                    data[key] = strip_markdown_bold_for_plain(flatten_display_text(data[key]))
                elif key == "description":
                    data[key] = clean_drug_plain_text(data[key])
                else:
                    data[key] = strip_markdown_bold_for_plain(clean_display_text(data[key]))
        if "sections" in data and isinstance(data["sections"], list):
            from .utils import is_junk_scraped_text

            cleaned = []
            for row in data["sections"]:
                if not isinstance(row, dict):
                    continue
                text = format_section_markdown(str(row.get("text") or ""))
                text = strip_markdown_bold_for_plain(text)
                if not text or is_junk_scraped_text(text) or is_registry_meta_text(text):
                    continue
                cleaned.append(
                    {
                        "key": row.get("key") or "",
                        "title": flatten_display_text(str(row.get("title") or "")),
                        "text": text,
                    }
                )
            data["sections"] = cleaned
        return data


class _CleanDiseaseTextMixin(_CleanDiseaseNameMixin):
    """Clean disease name + description/instructions for Flutter."""

    _TEXT_KEYS = ("description", "description_preview", "instructions")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in self._TEXT_KEYS:
            if key in data and isinstance(data[key], str):
                data[key] = strip_mkb_public_text(data[key])
        if "sections" in data and isinstance(data["sections"], list):
            cleaned = []
            for row in data["sections"]:
                if not isinstance(row, dict):
                    continue
                text = format_section_markdown(strip_mkb_public_text(str(row.get("text") or "")))
                text = strip_markdown_bold_for_plain(text)
                if not text:
                    continue
                cleaned.append(
                    {
                        "key": row.get("key") or "",
                        "title": flatten_display_text(str(row.get("title") or "")),
                        "text": text,
                    }
                )
            data["sections"] = cleaned
        return data


class DiseaseSerializer(_CleanDiseaseTextMixin, serializers.ModelSerializer):
    description = serializers.SerializerMethodField()
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview", "created_at", "updated_at")

    def get_description(self, obj: Disease) -> str:
        return disease_card_text(obj)

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(disease_card_text(obj))


class DiseaseSearchSerializer(_CleanDiseaseNameMixin, serializers.ModelSerializer):
    """
    Лёгкий список/поиск. Не трогаем instructions (иначе N+1 и 10с на весь каталог).
    """

    description = serializers.SerializerMethodField()
    description_preview = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = ("id", "name", "description", "description_preview")

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(strip_mkb_public_text(obj.description or ""), max_chars=140)

    def get_description(self, obj: Disease) -> str:
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
        from .instruction_sections import fallback_drug_overview
        from .utils import flatten_display_text

        raw = flatten_display_text(obj.description or "")
        if len(raw) >= 60:
            return description_preview(raw, max_chars=180)
        return description_preview(
            fallback_drug_overview(name=obj.name or "", dosage=obj.dosage or ""),
            max_chars=180,
        )

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
        return description_preview(disease_card_text(obj), max_chars=120)
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


class DiseaseDetailSerializer(_CleanDiseaseTextMixin, serializers.ModelSerializer):
    """Карточка заболевания + лёгкий список лекарств (без рекурсии)."""

    description_preview = serializers.SerializerMethodField()
    drugs = serializers.SerializerMethodField()
    related_drugs = serializers.SerializerMethodField()
    drugs_count = serializers.SerializerMethodField()
    drugs_truncated = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Disease
        fields = (
            "id",
            "name",
            "description",
            "description_preview",
            "instructions",
            "sections",
            "drugs",
            "related_drugs",
            "drugs_count",
            "drugs_truncated",
            "created_at",
            "updated_at",
        )

    def get_description_preview(self, obj: Disease) -> str:
        return description_preview(disease_card_text(obj))

    def get_sections(self, obj: Disease) -> list:
        from .disease_sections import build_disease_sections, fallback_disease_labeled

        sections = build_disease_sections(
            description=obj.description or "",
            instructions=getattr(obj, "instructions", "") or "",
        )
        if sections:
            return sections
        labeled = fallback_disease_labeled(obj.name or "")
        return build_disease_sections(description="", instructions="", stored=labeled)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # List/detail cards: if description is only MKB boilerplate, show real overview.
        card = disease_card_text(instance)
        if card and (
            "Код диагноза по Международной классификации" in (data.get("description") or "")
            or len(clean_display_text(data.get("description") or "")) < 80
        ):
            data["description"] = card
        if "description_preview" in data:
            data["description_preview"] = description_preview(card)
        return data

    def _drugs_queryset(self, obj: Disease):
        try:
            qs = obj.drugs.filter(is_active=True)
        except Exception:
            qs = obj.drugs.all()
        q = (self.context.get("drug_q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(name__icontains=q) | Q(dosage__icontains=q))
        return qs.only("id", "name", "description", "dosage", "image", "rating").order_by("name")

    def _drug_list(self, obj: Disease) -> list:
        if self.context.get("skip_drugs"):
            return []
        cache_key = (
            obj.pk,
            (self.context.get("drug_q") or "").strip().casefold(),
            self.context.get("highlight_drug_id"),
            int(self.context.get("drugs_limit") or 300),
        )
        cache = self.context.setdefault("_disease_drug_payload", {})
        if cache_key in cache:
            return cache[cache_key]

        limit = int(self.context.get("drugs_limit") or 300)
        limit = max(40, min(limit, 1000))
        highlight_id = self.context.get("highlight_drug_id")

        qs = self._drugs_queryset(obj)
        rows = list(qs[:limit])
        by_id = {d.id: d for d in rows}

        # Circular nav: drug → disease → drugs must still show the source drug
        # (alphabetical [:40] used to drop «Креон» when disease has 200+ drugs).
        if highlight_id:
            highlighted = by_id.get(highlight_id)
            if highlighted is None:
                try:
                    highlighted = (
                        obj.drugs.filter(pk=highlight_id)
                        .only("id", "name", "description", "dosage", "image", "rating")
                        .first()
                    )
                except Exception:
                    highlighted = None
            if highlighted is not None:
                rows = [highlighted] + [d for d in rows if d.id != highlighted.id]
                if len(rows) > limit:
                    rows = rows[:limit]

        data = DrugMiniPublicSerializer(rows, many=True, context=self.context).data
        cache[cache_key] = data
        return data

    def get_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)

    def get_related_drugs(self, obj: Disease) -> list:
        return self._drug_list(obj)

    def get_drugs_count(self, obj: Disease) -> int:
        if self.context.get("skip_drugs"):
            return 0
        try:
            return self._drugs_queryset(obj).count()
        except Exception:
            return obj.drugs.count()

    def get_drugs_truncated(self, obj: Disease) -> bool:
        if self.context.get("skip_drugs"):
            return False
        limit = int(self.context.get("drugs_limit") or 300)
        return self.get_drugs_count(obj) > limit


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
        from .instruction_sections import fallback_drug_overview
        from .utils import flatten_display_text

        raw = flatten_display_text(obj.description or "")
        if len(raw) >= 80:
            return description_preview(raw, max_chars=220)
        return description_preview(
            fallback_drug_overview(name=obj.name or "", dosage=obj.dosage or ""),
            max_chars=220,
        )

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
    """Полная карточка лекарства + болезни + секции инструкции (спойлеры как у Vidal)."""

    diseases = serializers.SerializerMethodField()
    related_diseases = serializers.SerializerMethodField()
    in_my_cabinet = serializers.SerializerMethodField()
    description_preview = serializers.SerializerMethodField()
    instructions_preview = serializers.SerializerMethodField()
    inn = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

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
            "inn",
            "image",
            "rating",
            "sections",
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
        """
        Always light disease cards (id/name/preview).
        Never nest drugs here — that made FE use include_related=false and
        showed «Связанные заболевания не указаны» even when links exist.
        """
        cache = self.context.setdefault("_drug_disease_payload", {})
        if obj.pk in cache:
            return cache[obj.pk]
        qs = obj.diseases.only("id", "name", "description").order_by("name")[:40]
        data = DiseaseMiniPublicSerializer(qs, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)

    def get_related_diseases(self, obj: Drug) -> list:
        return self._disease_list(obj)

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description, max_chars=200)

    def get_instructions_preview(self, obj: Drug) -> str:
        from .instruction_sections import build_drug_sections

        sections = build_drug_sections(
            name=obj.name or "",
            description=obj.description or "",
            instructions=obj.instructions or "",
            dosage=obj.dosage or "",
        )
        if sections:
            blob = "\n\n".join(row["text"] for row in sections[:3])
            return description_preview(blob, max_chars=200)
        return description_preview(obj.instructions, max_chars=200)

    def get_inn(self, obj: Drug) -> str:
        from .utils import extract_drug_mnn

        return extract_drug_mnn(obj.description or "") or extract_drug_mnn(obj.instructions or "")

    def get_sections(self, obj: Drug) -> list:
        from .instruction_sections import build_drug_sections

        return build_drug_sections(
            name=obj.name or "",
            description=obj.description or "",
            instructions=obj.instructions or "",
            dosage=obj.dosage or "",
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        sections = data.get("sections") or []
        from .utils import is_junk_scraped_text

        if sections:
            from .instruction_sections import compose_drug_description

            composed = compose_drug_description(
                name=instance.name or "",
                description=instance.description or "",
                instructions=instance.instructions or "",
                dosage=instance.dosage or "",
                inn=data.get("inn") or "",
                sections=sections,
            )
            data["description"] = composed
            data["description_preview"] = description_preview(composed, max_chars=240)
            data["instructions"] = strip_markdown_bold_for_plain(
                "\n\n".join(
                    f"{row.get('title') or ''}\n\n{row.get('text') or ''}" for row in sections
                )
            )
        elif is_junk_scraped_text(data.get("instructions") or ""):
            data["instructions"] = ""
            data["instructions_preview"] = ""
        else:
            from .instruction_sections import fallback_drug_overview

            data["description"] = fallback_drug_overview(
                name=instance.name or "",
                dosage=instance.dosage or "",
                inn=data.get("inn") or "",
            )
            data["description_preview"] = description_preview(data["description"], max_chars=240)
        return data

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
