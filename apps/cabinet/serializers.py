from __future__ import annotations

from rest_framework import serializers

from apps.catalog.serializers import DrugSerializer

from .models import CabinetItem


class CabinetItemSerializer(serializers.ModelSerializer):
    drug_detail = DrugSerializer(source="drug", read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = CabinetItem
        fields = (
            "id",
            "drug",
            "drug_detail",
            "custom_name",
            "expires_at",
            "note",
            "photo",
            "display_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("display_name", "drug_detail", "created_at", "updated_at")

    def get_display_name(self, obj: CabinetItem) -> str:
        return obj.display_name()

    def validate(self, attrs):
        if self.instance is None:
            drug = attrs.get("drug")
            custom = (attrs.get("custom_name") or "").strip()
            if not drug and not custom:
                raise serializers.ValidationError("Укажите drug (id из справочника) или custom_name.")
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        return CabinetItem.objects.create(user=user, **validated_data)
