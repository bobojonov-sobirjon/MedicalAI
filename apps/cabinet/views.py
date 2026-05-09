from __future__ import annotations

from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q

from apps.catalog.models import Drug, DrugViewLog
from apps.catalog.serializers import DrugSerializer

from .models import CabinetItem
from .serializers import CabinetItemSerializer
from .services import recognize_cabinet_upload


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
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Аптечка"],
        summary="Распознать лекарство по фото",
        description="multipart: поле `image` (файл). Возвращает строку и при возможности совпадение из справочника.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "format": "binary", "description": "Фото упаковки/этикетки."},
                },
                "required": ["image"],
            },
        },
        responses={
            200: inline_serializer(
                name="CabinetRecognizeResponse",
                fields={
                    "recognized_name": serializers.CharField(),
                    "matched_drug_id": serializers.IntegerField(allow_null=True),
                    "matched_drug": serializers.JSONField(
                        allow_null=True,
                        help_text="Объект лекарства (как в DrugSerializer) или null.",
                    ),
                },
            ),
        },
    )
    def post(self, request):
        upload = request.FILES.get("image")
        if not upload:
            return Response({"detail": "Поле image обязательно."}, status=status.HTTP_400_BAD_REQUEST)
        upload.seek(0)
        raw = upload.read()
        mime = upload.content_type or "image/jpeg"
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            mime = "image/jpeg"
        upload.seek(0)
        data = recognize_cabinet_upload(raw, mime, source_file=upload)
        drug = data["matched_drug"]
        return Response(
            {
                "recognized_name": data["recognized_name"],
                "matched_drug_id": data["matched_drug_id"],
                "matched_drug": DrugSerializer(drug, context={"request": request}).data if drug else None,
            }
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
