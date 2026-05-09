from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BodyPart, Disease, Drug, Symptom
from .serializers import (
    BodyPartSerializer,
    DiseaseDetailSerializer,
    DiseaseSerializer,
    DrugSerializer,
    SymptomSerializer,
)


def _query_param(request, name: str, default: str = "") -> str:
    return (request.query_params.get(name) or default).strip()


class PublicDiseaseListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Заболевания"],
        summary="Список заболеваний",
        parameters=[
            OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию"),
        ],
    )
    def get(self, request):
        q = _query_param(request, "q")
        qs = Disease.objects.all().order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q))
        return Response(DiseaseSerializer(qs, many=True, context={"request": request}).data)


class PublicDiseaseDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Заболевания"], summary="Получить заболевание (с лекарствами)")
    def get(self, request, pk: int):
        obj = get_object_or_404(Disease.objects.prefetch_related("drugs"), pk=pk)
        return Response(DiseaseDetailSerializer(obj, context={"request": request}).data)


class SymptomSearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Помощник"],
        summary="Поиск симптомов (автодополнение)",
        description=(
            "Используется на экране «Помощник» для подсказок при вводе симптомов. "
            "Возвращает до 40 совпадений по подстроке в названии симптома."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=True,
                description="Подстрока для поиска симптома (автодополнение)",
            )
        ],
        responses=SymptomSerializer(many=True),
    )
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 1:
            return Response([])
        qs = Symptom.objects.filter(name__icontains=q).order_by("name")[:40]
        return Response(SymptomSerializer(qs, many=True).data)


class BodyPartListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Помощник"],
        summary="Части тела для «Помощника»",
        description=(
            "Справочник частей тела для UI (клик по области тела). "
            "Фронтенд использует `code` как стабильный идентификатор, а `label` — для отображения."
        ),
        responses=BodyPartSerializer(many=True),
    )
    def get(self, request):
        qs = BodyPart.objects.all().order_by("sort_order", "label")
        return Response(BodyPartSerializer(qs, many=True).data)

class PublicDrugListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Лекарства"],
        summary="Список лекарств",
        parameters=[OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию")],
    )
    def get(self, request):
        q = _query_param(request, "q")
        qs = Drug.objects.all().order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q))
        return Response(DrugSerializer(qs, many=True, context={"request": request}).data)


class PublicDrugDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Лекарства"], summary="Получить лекарство")
    def get(self, request, pk: int):
        obj = Drug.objects.get(pk=pk)
        return Response(DrugSerializer(obj, context={"request": request}).data)

