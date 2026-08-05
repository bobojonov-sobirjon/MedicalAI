from __future__ import annotations

from rest_framework import serializers

from apps.catalog.models import Drug
from apps.catalog.serializers import DiseaseMiniPublicSerializer
from apps.catalog.utils import description_preview

from .models import CabinetItem
from .services import match_drug_by_name


class CabinetCatalogDrugSerializer(serializers.ModelSerializer):
    """
    Карточка лекарства из справочника для аптечки.
    Описание, инструкция и болезни читаются из БД catalog.
    """

    description_preview = serializers.SerializerMethodField()
    instructions_preview = serializers.SerializerMethodField()
    diseases = serializers.SerializerMethodField()
    related_diseases = serializers.SerializerMethodField()

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
        )
        read_only_fields = fields

    def get_description_preview(self, obj: Drug) -> str:
        return description_preview(obj.description, max_chars=200)

    def get_instructions_preview(self, obj: Drug) -> str:
        return description_preview(obj.instructions, max_chars=200)

    def _diseases(self, obj: Drug) -> list:
        cache = self.context.setdefault("_cabinet_drug_diseases", {})
        if obj.pk in cache:
            return cache[obj.pk]
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "diseases" in prefetched:
            rows = sorted(prefetched["diseases"], key=lambda d: d.name)[:40]
        else:
            rows = list(obj.diseases.only("id", "name", "description").order_by("name")[:40])
        data = DiseaseMiniPublicSerializer(rows, many=True, context=self.context).data
        cache[obj.pk] = data
        return data

    def get_diseases(self, obj: Drug) -> list:
        return self._diseases(obj)

    def get_related_diseases(self, obj: Drug) -> list:
        return self._diseases(obj)


class CabinetItemSerializer(serializers.ModelSerializer):
    """
    Запись аптечки: лекарство и связанные болезни всегда из каталога (БД).
    """

    drug_id = serializers.PrimaryKeyRelatedField(
        source="drug",
        queryset=Drug.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="ID лекарства из справочника GET /api/catalog/drugs/",
    )
    drug_detail = CabinetCatalogDrugSerializer(source="drug", read_only=True)
    diseases = serializers.SerializerMethodField(
        help_text="Болезни из справочника, связанные с этим лекарством."
    )
    display_name = serializers.SerializerMethodField()
    catalog_drug_id = serializers.SerializerMethodField()

    class Meta:
        model = CabinetItem
        fields = (
            "id",
            "drug_id",
            "catalog_drug_id",
            "drug_detail",
            "diseases",
            "custom_name",
            "expires_at",
            "note",
            "photo",
            "display_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "display_name",
            "drug_detail",
            "diseases",
            "catalog_drug_id",
            "created_at",
            "updated_at",
        )

    def get_catalog_drug_id(self, obj: CabinetItem) -> int | None:
        return obj.drug_id

    def get_display_name(self, obj: CabinetItem) -> str:
        return obj.display_name()

    def get_diseases(self, obj: CabinetItem) -> list:
        if not obj.drug_id:
            return []
        return CabinetCatalogDrugSerializer(context=self.context)._diseases(obj.drug)

    def to_internal_value(self, data):
        # FE may send "drug": 123 instead of "drug_id"
        if hasattr(data, "copy"):
            data = data.copy()
            if data.get("drug_id") in (None, "") and data.get("drug") not in (None, ""):
                data["drug_id"] = data.get("drug")
        return super().to_internal_value(data)

    def validate(self, attrs):
        custom = (attrs.get("custom_name") or getattr(self.instance, "custom_name", "") or "").strip()
        if "custom_name" in attrs:
            custom = (attrs.get("custom_name") or "").strip()

        drug = attrs.get("drug", getattr(self.instance, "drug", None) if self.instance else None)

        if self.instance is None:
            if drug is None and custom:
                matched, _ = match_drug_by_name(custom)
                if matched:
                    attrs["drug"] = matched
                    if matched.name.casefold() == custom.casefold():
                        attrs["custom_name"] = ""
                    drug = matched
                else:
                    raise serializers.ValidationError(
                        {
                            "drug_id": (
                                "Укажите drug_id из справочника лекарств "
                                "(GET /api/catalog/drugs/?q=...). "
                                f"Препарат «{custom}» в базе не найден."
                            )
                        }
                    )
            if attrs.get("drug") is None:
                raise serializers.ValidationError(
                    {
                        "drug_id": (
                            "Обязательно: drug_id из справочника лекарств. "
                            "Все данные аптечки подгружаются из базы лекарств и болезней."
                        )
                    }
                )
        elif "drug" in attrs and attrs["drug"] is None:
            raise serializers.ValidationError(
                {"drug_id": "Нельзя отвязать запись аптечки от справочника лекарств."}
            )

        linked = attrs.get("drug") or drug
        if linked is not None and not linked.is_active:
            raise serializers.ValidationError({"drug_id": "Это лекарство скрыто в справочнике."})

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        drug = validated_data.get("drug")
        if drug is not None:
            existing = CabinetItem.objects.filter(user=user, drug=drug).first()
            if existing:
                raise serializers.ValidationError(
                    {"drug_id": f"Это лекарство уже есть в аптечке (запись id={existing.pk})."}
                )
        return CabinetItem.objects.create(user=user, **validated_data)
