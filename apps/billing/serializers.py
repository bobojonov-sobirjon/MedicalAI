from __future__ import annotations

from rest_framework import serializers

from .models import Payment, TariffPlan


class TariffPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffPlan
        fields = (
            "slug",
            "tier",
            "title",
            "description",
            "price_rub",
            "validity_days",
            "limits",
        )


class CreatePaymentSerializer(serializers.Serializer):
    tariff_slug = serializers.SlugField(help_text="standard или premium")


class PaymentSerializer(serializers.ModelSerializer):
    tariff_slug = serializers.CharField(source="tariff.slug", read_only=True)
    tariff_title = serializers.CharField(source="tariff.title", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "tariff_slug",
            "tariff_title",
            "amount_rub",
            "status",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields


class PaymentStatusSerializer(serializers.ModelSerializer):
    """Статус платежа для polling после возврата с Robokassa."""

    payment_id = serializers.IntegerField(source="id")
    tariff_slug = serializers.CharField(source="tariff.slug", read_only=True)
    tariff_title = serializers.CharField(source="tariff.title", read_only=True)
    is_paid = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "payment_id",
            "status",
            "is_paid",
            "amount_rub",
            "tariff_slug",
            "tariff_title",
            "paid_at",
            "created_at",
        )

    def get_is_paid(self, obj: Payment) -> bool:
        return obj.status == Payment.Status.PAID
