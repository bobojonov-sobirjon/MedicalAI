from __future__ import annotations

import httpx
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q

from apps.catalog.models import Drug, DrugViewLog
from apps.catalog.serializers import DrugSerializer
from apps.core.gemini import GeminiConfigError
from apps.core.rutronix import (
    RuTronixConfigError,
    RuTronixPaymentRequired,
    RuTronixUnauthorized,
    RuTronixUpstreamError,
)

from .models import CabinetItem
from .serializers import CabinetItemSerializer
from .services import (
    build_recognition_result,
    recognize_cabinet_batch,
    recognize_cabinet_upload,
)


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_image_upload(request):
    upload = request.FILES.get("image")
    if not upload:
        return None, None, None
    upload.seek(0)
    raw = upload.read()
    mime = upload.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        mime = "image/jpeg"
    upload.seek(0)
    return upload, raw, mime


def _serialize_recognition(request, result: dict) -> dict:
    drug = result.get("matched_drug")
    cabinet_item = result.get("cabinet_item")
    return {
        "recognized_name": result.get("recognized_name") or "",
        "matched_drug_id": result.get("matched_drug_id"),
        "matched_drug": DrugSerializer(drug, context={"request": request}).data if drug else None,
        "added_to_cabinet": bool(result.get("added_to_cabinet")),
        "already_in_cabinet": bool(result.get("already_in_cabinet")),
        "cabinet_item": (
            CabinetItemSerializer(cabinet_item, context={"request": request}).data if cabinet_item else None
        ),
    }


class CabinetItemListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Аптечка"],
        summary="Список моей аптечки",
        parameters=[
            OpenApiParameter(name="q", type=str, required=False, description="Поиск по названию (drug.name или custom_name)"),
        ],
    )
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        qs = CabinetItem.objects.filter(user=request.user).select_related("drug")
        if q:
            qs = qs.filter(Q(drug__name__icontains=q) | Q(custom_name__icontains=q))
        qs = qs.order_by("-expires_at", "-created_at")
        return Response(CabinetItemSerializer(qs, many=True, context={"request": request}).data)

    @extend_schema(tags=["Аптечка"], summary="Добавить в аптечку", request=CabinetItemSerializer)
    def post(self, request):
        s = CabinetItemSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data, status=status.HTTP_201_CREATED)


class CabinetItemDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk: int) -> CabinetItem:
        return CabinetItem.objects.select_related("drug").get(pk=pk, user=request.user)

    @extend_schema(tags=["Аптечка"], summary="Одна запись аптечки")
    def get(self, request, pk: int):
        obj = self._get(request, pk)
        return Response(CabinetItemSerializer(obj, context={"request": request}).data)

    @extend_schema(tags=["Аптечка"], summary="Обновить запись", request=CabinetItemSerializer)
    def patch(self, request, pk: int):
        obj = self._get(request, pk)
        s = CabinetItemSerializer(obj, data=request.data, partial=True, context={"request": request})
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    @extend_schema(tags=["Аптечка"], summary="Удалить из аптечки")
    def delete(self, request, pk: int):
        CabinetItem.objects.filter(pk=pk, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CabinetRecognizeView(APIView):
    """
    Распознавание лекарств по фото (одна упаковка или несколько на одном снимке).
    Опционально сразу добавляет найденные препараты в аптечку.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Аптечка"],
        summary="Распознать лекарство(а) по фото",
        description=(
            "multipart: поле `image` (файл).\n\n"
            "- `mode=single` (по умолчанию) — одна упаковка, ответ как раньше + поля added_to_cabinet.\n"
            "- `mode=batch` — все видимые упаковки на фото, ответ `{ items: [...], count }`.\n"
            "- `add_to_cabinet=true` — сразу добавить распознанные препараты в аптечку "
            "(дубликаты пропускаются, already_in_cabinet=true)."
        ),
        parameters=[
            OpenApiParameter(
                name="mode",
                type=str,
                required=False,
                enum=["single", "batch"],
                description="single — одна упаковка; batch — несколько на одном фото.",
            ),
            OpenApiParameter(
                name="add_to_cabinet",
                type=bool,
                required=False,
                description="true — сразу добавить в аптечку после распознавания.",
            ),
        ],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "format": "binary", "description": "Фото упаковки или нескольких упаковок."},
                    "mode": {"type": "string", "enum": ["single", "batch"]},
                    "add_to_cabinet": {"type": "boolean"},
                },
                "required": ["image"],
            },
        },
        responses={
            200: inline_serializer(
                name="CabinetRecognizeResponse",
                fields={
                    "mode": serializers.CharField(),
                    "recognized_name": serializers.CharField(required=False),
                    "matched_drug_id": serializers.IntegerField(required=False, allow_null=True),
                    "matched_drug": serializers.JSONField(required=False, allow_null=True),
                    "added_to_cabinet": serializers.BooleanField(required=False),
                    "already_in_cabinet": serializers.BooleanField(required=False),
                    "cabinet_item": serializers.JSONField(required=False, allow_null=True),
                    "items": serializers.ListField(required=False, child=serializers.DictField()),
                    "count": serializers.IntegerField(required=False),
                },
            ),
        },
    )
    def post(self, request):
        upload, raw, mime = _read_image_upload(request)
        if not upload:
            return Response({"detail": "Поле image обязательно."}, status=status.HTTP_400_BAD_REQUEST)

        mode = (request.data.get("mode") or request.query_params.get("mode") or "single").strip().lower()
        if mode not in {"single", "batch"}:
            return Response({"detail": "mode должен быть single или batch."}, status=status.HTTP_400_BAD_REQUEST)

        add_to_cabinet = _parse_bool(
            request.data.get("add_to_cabinet", request.query_params.get("add_to_cabinet"))
        )

        try:
            if mode == "batch":
                recognitions = recognize_cabinet_batch(raw, mime)
                items = [
                    _serialize_recognition(
                        request,
                        build_recognition_result(
                            request.user,
                            row,
                            add_to_cabinet=add_to_cabinet,
                        ),
                    )
                    for row in recognitions
                ]
                return Response({"mode": "batch", "items": items, "count": len(items)})

            recognition = recognize_cabinet_upload(raw, mime, source_file=upload)
            payload = _serialize_recognition(
                request,
                build_recognition_result(
                    request.user,
                    recognition,
                    add_to_cabinet=add_to_cabinet,
                    photo=upload if add_to_cabinet else None,
                ),
            )
            return Response({"mode": "single", **payload})
        except (GeminiConfigError, RuTronixConfigError):
            return Response(
                {"detail": "Не настроен ключ ИИ: задайте RUTRONIX_API_KEY (рекомендуется) или GEMINI_API_KEY."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except RuTronixUnauthorized:
            return Response(
                {"detail": "Неверный RUTRONIX_API_KEY. Проверьте ключ в .env."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except RuTronixPaymentRequired:
            return Response(
                {"detail": "Недостаточно баланса RuTronix. Пополните счёт или задайте GEMINI_API_KEY как запасной вариант."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (RuTronixUpstreamError, httpx.HTTPStatusError) as exc:
            return Response(
                {
                    "detail": (
                        "Сервис распознавания RuTronix временно недоступен. "
                        "Повторите позже или задайте GEMINI_API_KEY в .env."
                    ),
                    "error": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except httpx.TimeoutException:
            return Response(
                {
                    "detail": (
                        "Таймаут ответа ИИ при распознавании. Увеличьте RUTRONIX_VISION_TIMEOUT_S "
                        "и gunicorn --timeout на сервере."
                    )
                },
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )


class RecentDrugViewsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Аптечка"],
        summary="Недавно просмотренные лекарства",
        parameters=[OpenApiParameter(name="limit", type=int, required=False, description="По умолчанию 30")],
    )
    def get(self, request):
        limit = min(int(request.query_params.get("limit") or 30), 100)
        logs = (
            DrugViewLog.objects.filter(user=request.user)
            .select_related("drug")
            .order_by("-viewed_at")[:limit]
        )
        drugs = [log.drug for log in logs if log.drug_id]
        return Response(
            {
                "title": "Ранее просмотренные лекарства",
                "items": DrugSerializer(drugs, many=True, context={"request": request}).data,
            }
        )


class DrugRecordViewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Просмотры лекарств"],
        summary="Записать просмотр лекарства",
        description=(
            "Создаёт/обновляет запись просмотра в БД (DrugViewLog) — это действие с побочным эффектом, "
            "поэтому используется POST, а не GET (GET не должен менять состояние сервера). "
            "Список «ранее просмотренные» читать: GET /api/me/recent-drugs/."
        ),
        request=inline_serializer(name="DrugViewLogEmptyBody", fields={}),
        responses={
            200: inline_serializer(
                name="DrugViewLogOk",
                fields={
                    "ok": serializers.BooleanField(),
                    "drug_id": serializers.IntegerField(),
                },
            ),
        },
    )
    def post(self, request, pk: int):
        drug = Drug.objects.filter(pk=pk).first()
        if not drug:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        log, _created = DrugViewLog.objects.get_or_create(user=request.user, drug=drug)
        log.save()
        return Response({"ok": True, "drug_id": drug.id}, status=status.HTTP_200_OK)
