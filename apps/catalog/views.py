from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Disease, Drug
from .serializers import DiseaseSerializer, DrugSerializer


def _query_param(request, name: str, default: str = "") -> str:
    return (request.query_params.get(name) or default).strip()


class PublicDiseaseListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Diseases"],
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

    @extend_schema(tags=["Diseases"], summary="Получить заболевание")
    def get(self, request, pk: int):
        obj = Disease.objects.get(pk=pk)
        return Response(DiseaseSerializer(obj, context={"request": request}).data)

class PublicDrugListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Drugs"],
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

    @extend_schema(tags=["Drugs"], summary="Получить лекарство")
    def get(self, request, pk: int):
        obj = Drug.objects.get(pk=pk)
        return Response(DrugSerializer(obj, context={"request": request}).data)

