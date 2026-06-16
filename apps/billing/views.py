from __future__ import annotations

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment, TariffPlan
from .serializers import (
    CreatePaymentSerializer,
    PaymentSerializer,
    PaymentStatusSerializer,
    TariffPlanSerializer,
)
from .services import create_payment_for_tariff, subscription_status_payload


class TariffListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Оплата"],
        summary="Список тарифов",
        description="Публичный список активных тарифов (покупаемых и описание).",
        responses=TariffPlanSerializer(many=True),
    )
    def get(self, request):
        qs = TariffPlan.objects.filter(is_active=True).order_by("sort_order", "id")
        return Response(TariffPlanSerializer(qs, many=True).data)


class MySubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Оплата"],
        summary="Моя подписка",
        description="Текущий тариф, срок действия, лимиты и флаг использования trial.",
    )
    def get(self, request):
        return Response(subscription_status_payload(request.user))


class CreatePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Оплата"],
        summary="Создать платёж и получить ссылку Robokassa",
        description=(
            "Пользователь выбирает тариф **standard** или **premium**.\n\n"
            "Ответ содержит **payment_url** — официальная страница оплаты Robokassa "
            "(`https://auth.robokassa.ru/...`). Откройте её в **браузере или WebView** — "
            "внутри приложения своя форма оплаты не нужна.\n\n"
            "После оплаты Robokassa вызывает серверный callback; статус проверяйте через "
            "`GET /api/billing/payments/<payment_id>/` (polling каждые 2–3 сек) "
            "или `GET /api/billing/subscription/`."
        ),
        request=CreatePaymentSerializer,
        responses={
            201: inline_serializer(
                name="CreatePaymentResponse",
                fields={
                    "payment_id": serializers.IntegerField(),
                    "status": serializers.CharField(),
                    "payment_url": serializers.URLField(
                        help_text="Ссылка на страницу Robokassa — открыть в WebView/браузере"
                    ),
                    "amount_rub": serializers.DecimalField(max_digits=10, decimal_places=2),
                    "tariff_slug": serializers.CharField(),
                    "tariff_title": serializers.CharField(),
                },
            )
        },
    )
    def post(self, request):
        s = CreatePaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            payment, url = create_payment_for_tariff(request.user, s.validated_data["tariff_slug"])
        except TariffPlan.DoesNotExist:
            return Response({"detail": "Тариф не найден или недоступен для покупки."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "payment_id": payment.pk,
                "status": payment.status,
                "payment_url": url,
                "amount_rub": payment.amount_rub,
                "tariff_slug": payment.tariff.slug,
                "tariff_title": payment.tariff.title,
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentDetailView(APIView):
    """Проверка статуса платежа после возврата с Robokassa."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Оплата"],
        summary="Статус платежа по ID",
        description=(
            "После открытия `payment_url` и оплаты на стороне Robokassa опрашивайте этот endpoint "
            "(например раз в 2–3 секунды), пока `status` не станет `paid` или не истечёт таймаут.\n\n"
            "При `paid` в ответе также будет актуальная подписка."
        ),
        responses={
            200: inline_serializer(
                name="PaymentStatusResponse",
                fields={
                    "payment_id": serializers.IntegerField(),
                    "status": serializers.ChoiceField(choices=["pending", "paid", "failed", "cancelled"]),
                    "is_paid": serializers.BooleanField(),
                    "amount_rub": serializers.DecimalField(max_digits=10, decimal_places=2),
                    "tariff_slug": serializers.CharField(),
                    "tariff_title": serializers.CharField(),
                    "paid_at": serializers.DateTimeField(allow_null=True),
                    "created_at": serializers.DateTimeField(),
                    "subscription": serializers.JSONField(allow_null=True),
                },
            )
        },
    )
    def get(self, request, payment_id: int):
        payment = Payment.objects.filter(pk=payment_id, user=request.user).select_related("tariff").first()
        if not payment:
            return Response({"detail": "Платёж не найден."}, status=status.HTTP_404_NOT_FOUND)
        data = PaymentStatusSerializer(payment).data
        if payment.status == Payment.Status.PAID:
            data["subscription"] = subscription_status_payload(request.user)
        else:
            data["subscription"] = None
        return Response(data)


class MyPaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Оплата"],
        summary="История платежей",
        responses=PaymentSerializer(many=True),
    )
    def get(self, request):
        qs = Payment.objects.filter(user=request.user).select_related("tariff").order_by("-created_at")[:50]
        return Response(PaymentSerializer(qs, many=True).data)


@method_decorator(csrf_exempt, name="dispatch")
class RobokassaResultView(APIView):
    """Result URL — серверный callback Robokassa (ТЗ §4.2)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        return self._handle(request)

    def get(self, request):
        return self._handle(request)

    def _handle(self, request):
        data = request.POST if request.method == "POST" else request.GET
        out_sum = (data.get("OutSum") or "").strip()
        inv_id_raw = (data.get("InvId") or "").strip()
        signature = (data.get("SignatureValue") or "").strip()
        if not out_sum or not inv_id_raw or not signature:
            return HttpResponse("bad request", status=400)
        try:
            inv_id = int(inv_id_raw)
        except ValueError:
            return HttpResponse("bad inv", status=400)
        from .services import process_robokassa_result

        try:
            process_robokassa_result(
                out_sum=out_sum,
                inv_id=inv_id,
                signature_value=signature,
                payload=dict(data.items()),
            )
        except Payment.DoesNotExist:
            return HttpResponse("not found", status=404)
        except ValueError:
            return HttpResponse("error", status=400)
        return HttpResponse(f"OK{inv_id}")


class RobokassaSuccessView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Оплата"],
        summary="Success URL (редирект после успешной оплаты на Robokassa)",
        description=(
            "Пользователь попадает сюда после Successful в демо-режиме. "
            "Если в query есть OutSum, InvId, SignatureValue — платёж подтверждается (Password1)."
        ),
    )
    def get(self, request):
        out_sum = (request.GET.get("OutSum") or "").strip()
        inv_id_raw = (request.GET.get("InvId") or "").strip()
        signature = (request.GET.get("SignatureValue") or "").strip()

        if out_sum and inv_id_raw and signature:
            try:
                inv_id = int(inv_id_raw)
                from .services import process_robokassa_success

                payment = process_robokassa_success(
                    out_sum=out_sum,
                    inv_id=inv_id,
                    signature_value=signature,
                    payload=dict(request.GET.items()),
                )
                return Response(
                    {
                        "ok": True,
                        "message": "Оплата подтверждена. Вернитесь в приложение.",
                        "payment_id": payment.pk,
                        "status": payment.status,
                    }
                )
            except Payment.DoesNotExist:
                return Response({"ok": False, "detail": "Платёж не найден."}, status=status.HTTP_404_NOT_FOUND)
            except ValueError as exc:
                return Response({"ok": False, "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        inv_id = request.GET.get("InvId") or request.GET.get("inv_id")
        return Response(
            {
                "ok": True,
                "message": "Оплата принята. Вернитесь в приложение.",
                "payment_id": int(inv_id) if inv_id and str(inv_id).isdigit() else None,
            }
        )


class RobokassaFailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Оплата"], summary="Fail URL (редирект пользователя)")
    def get(self, request):
        return Response({"ok": False, "message": "Оплата не завершена."})
