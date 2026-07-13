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
        try:
            limit = min(int(request.query_params.get("limit") or (200 if q else 500)), 2000)
        except (TypeError, ValueError):
            limit = 200 if q else 500
        qs = Disease.objects.all().order_by("name")
        if q:
            # История болезней / автокомплит: по названию и описанию (МКБ-код тоже в description).
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
            # Короткие совпадения по названию выше длинных МКБ-формулировок.
            from django.db.models import Case, IntegerField, Value, When

            qs = qs.annotate(
                _rank=Case(
                    When(name__iexact=q, then=Value(0)),
                    When(name__istartswith=q, then=Value(1)),
                    When(name__icontains=q, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            ).order_by("_rank", "name")
        return Response(DiseaseSerializer(qs[:limit], many=True, context={"request": request}).data)


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
        summary="Симптомы: список или поиск (автодополнение)",
        description=(
            "Используется на экране «Помощник». Если `q` не передан — возвращается "
            "полный список симптомов (до 200). Если `q` передан — поиск по подстроке "
            "в названии (до 40 совпадений)."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=False,
                description="Подстрока для поиска симптома. Если не передана — вернётся весь список.",
            )
        ],
        responses=SymptomSerializer(many=True),
    )
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        qs = Symptom.objects.all().order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(aliases__icontains=q))[:40]
        else:
            qs = qs[:200]
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
        try:
            limit = min(int(request.query_params.get("limit") or 500), 2000)
        except (TypeError, ValueError):
            limit = 500
        qs = Drug.objects.prefetch_related("diseases").all().order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q))
        return Response(DrugSerializer(qs[:limit], many=True, context={"request": request}).data)


class PublicDrugDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Лекарства"], summary="Получить лекарство")
    def get(self, request, pk: int):
        obj = get_object_or_404(Drug.objects.prefetch_related("diseases"), pk=pk)
        return Response(DrugSerializer(obj, context={"request": request}).data)

