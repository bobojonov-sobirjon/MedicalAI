from __future__ import annotations

from django.db.models import Case, IntegerField, Prefetch, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BodyPart, Disease, Drug, Symptom
from .serializers import (
    BodyPartSerializer,
    DiseaseDetailSerializer,
    DiseaseSearchSerializer,
    DiseaseSerializer,
    DrugListSerializer,
    DrugPickerSerializer,
    DrugSerializer,
    SymptomSerializer,
)


def _query_param(request, name: str, default: str = "") -> str:
    return (request.query_params.get(name) or default).strip()


def _int_param(request, name: str, default: int, *, min_v: int = 1, max_v: int = 100) -> int:
    try:
        value = int(request.query_params.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return min(max(value, min_v), max_v)


def _bool_param(request, name: str) -> bool | None:
    raw = (request.query_params.get(name) or "").strip().lower()
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return None


def _search_query(request) -> str:
    """History/catalog autocomplete: q | search | name | query."""
    for key in ("q", "search", "name", "query"):
        value = _query_param(request, key)
        if value:
            return value
    return ""


def _active_drugs_qs():
    """Filter is_active only if column exists (safe before/after migrate)."""
    qs = Drug.objects.all()
    try:
        Drug._meta.get_field("is_active")
        qs = qs.filter(is_active=True)
    except Exception:
        pass
    return qs


class PublicDiseaseListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Заболевания"],
        summary="Список заболеваний",
        parameters=[
            OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию"),
            OpenApiParameter(name="search", required=False, type=str, description="Алиас q"),
            OpenApiParameter(name="name", required=False, type=str, description="Алиас q (история болезней)"),
            OpenApiParameter(name="limit", required=False, type=int),
        ],
    )
    def get(self, request):
        """
        Flutter history picker:
        - sheet ochilganda `q` siz chaqiriladi va local filter qiladi
        - shuning uchun `q` bo'lmasa TO'LIQ katalog (array) qaytaramiz
        Response: JSON array (List), NOT {results: ...}
        """
        q = _search_query(request)
        qs = Disease.objects.all().only("id", "name", "description").order_by("name")

        if q:
            try:
                limit = min(int(request.query_params.get("limit") or 100), 500)
            except (TypeError, ValueError):
                limit = 100
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
            qs = qs.annotate(
                _rank=Case(
                    When(name__iexact=q, then=Value(0)),
                    When(name__istartswith=q, then=Value(1)),
                    When(name__icontains=q, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            ).order_by("_rank", "name")
            rows = list(qs[:limit])
            return Response(DiseaseSearchSerializer(rows, many=True, context={"request": request}).data)

        # Full catalog for local FE filter (history «Выберите болезнь»).
        try:
            limit = min(int(request.query_params.get("limit") or 50000), 50000)
        except (TypeError, ValueError):
            limit = 50000
        rows = list(qs[:limit])
        return Response(DiseaseSearchSerializer(rows, many=True, context={"request": request}).data)


class PublicDiseaseDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Заболевания"],
        summary="Получить заболевание (с лекарствами)",
        parameters=[
            OpenApiParameter(
                name="include_drugs",
                required=False,
                type=bool,
                description="false — только карточка болезни без списка лекарств (быстро).",
            ),
        ],
    )
    def get(self, request, pk: int):
        include_drugs = _bool_param(request, "include_drugs")
        if include_drugs is False:
            obj = get_object_or_404(Disease.objects.all(), pk=pk)
            return Response(
                DiseaseDetailSerializer(obj, context={"request": request, "skip_drugs": True}).data
            )

        # Light prefetch: drugs only, NO nested diseases (that caused hang/500).
        obj = get_object_or_404(
            Disease.objects.prefetch_related(
                Prefetch(
                    "drugs",
                    queryset=_active_drugs_qs()
                    .only("id", "name", "description", "dosage", "image", "rating")
                    .order_by("name"),
                )
            ),
            pk=pk,
        )
        return Response(DiseaseDetailSerializer(obj, context={"request": request}).data)


class SymptomSearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Помощник"],
        summary="Симптомы: список или поиск (автодополнение)",
        parameters=[
            OpenApiParameter(name="q", type=str, required=False),
        ],
        responses=SymptomSerializer(many=True),
    )
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        qs = Symptom.objects.all().only("id", "name", "aliases", "created_at", "updated_at").order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(aliases__icontains=q))[:40]
        else:
            qs = qs[:200]
        return Response(SymptomSerializer(qs, many=True).data)


@method_decorator(cache_page(60 * 30), name="dispatch")
class BodyPartListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Помощник"], summary="Части тела для «Помощника»", responses=BodyPartSerializer(many=True))
    def get(self, request):
        qs = BodyPart.objects.all().order_by("sort_order", "label")
        return Response(BodyPartSerializer(qs, many=True).data)


class PublicDrugListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Лекарства"],
        summary="Список лекарств (тот же каталог для «Лекарства» и истории болезней)",
        description=(
            "Раздел **Лекарства** и модалка **«Выберите препараты»** (история болезней) "
            "должны использовать **этот же** endpoint.\n\n"
            "**Правильно (как поиск в «Лекарства»):**\n"
            "`GET /api/catalog/drugs/?q=Креон&page=1&page_size=50`\n\n"
            "**Либо полный лёгкий список для локального фильтра в модалке:**\n"
            "`GET /api/catalog/drugs/?picker=1` → JSON **array** `[{id,name,dosage}, ...]`\n\n"
            "**Нельзя:** брать только `drugs` из карточки болезни "
            "(`GET /catalog/diseases/{id}/`) — там лишь связанные препараты, не весь каталог.\n"
            "**Нельзя:** грузить только `page=1` без `q` и фильтровать локально — список неполный.\n"
            "Поиск: `q` / `search` / `name` / `query`."
        ),
        parameters=[
            OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию/дозе"),
            OpenApiParameter(name="search", required=False, type=str, description="Алиас q"),
            OpenApiParameter(name="name", required=False, type=str, description="Алиас q"),
            OpenApiParameter(name="query", required=False, type=str, description="Алиас q"),
            OpenApiParameter(
                name="picker",
                required=False,
                type=bool,
                description="true — полный лёгкий список (array) для модалки истории болезней",
            ),
            OpenApiParameter(name="page", required=False, type=int),
            OpenApiParameter(name="page_size", required=False, type=int),
            OpenApiParameter(name="limit", required=False, type=int),
            OpenApiParameter(name="offset", required=False, type=int),
            OpenApiParameter(name="disease_id", required=False, type=int),
            OpenApiParameter(name="letter", required=False, type=str),
            OpenApiParameter(name="ordering", required=False, type=str),
            OpenApiParameter(name="has_diseases", required=False, type=bool),
            OpenApiParameter(name="has_image", required=False, type=bool),
            OpenApiParameter(name="include_diseases", required=False, type=bool),
        ],
    )
    def get(self, request):
        from django.db.models import Count

        q = _search_query(request)
        picker = _bool_param(request, "picker") is True
        letter = _query_param(request, "letter")
        ordering = _query_param(request, "ordering") or "name"
        disease_id_raw = _query_param(request, "disease_id")
        has_diseases = _bool_param(request, "has_diseases")
        has_image = _bool_param(request, "has_image")
        include_diseases = _bool_param(request, "include_diseases") is True

        allowed_ordering = {"name", "-name", "rating", "-rating", "created_at", "-created_at"}
        if ordering not in allowed_ordering:
            ordering = "name"

        qs = _active_drugs_qs().defer("instructions")

        # History modal: full catalog as JSON array (same source as «Лекарства»).
        if picker and not disease_id_raw:
            try:
                limit = min(int(request.query_params.get("limit") or 50000), 50000)
            except (TypeError, ValueError):
                limit = 50000
            if q:
                qs = qs.filter(Q(name__icontains=q) | Q(dosage__icontains=q)).order_by("name")
            else:
                qs = qs.order_by("name")
            rows = list(qs.only("id", "name", "dosage")[:limit])
            return Response(DrugPickerSerializer(rows, many=True).data)

        need_disease_count = has_diseases is not None or include_diseases
        if need_disease_count:
            qs = qs.annotate(diseases_count=Count("diseases", distinct=True))

        if disease_id_raw:
            try:
                disease_id = int(disease_id_raw)
            except ValueError:
                disease_id = 0
            if disease_id > 0:
                qs = qs.filter(diseases__id=disease_id)

        if letter:
            qs = qs.filter(name__istartswith=letter[:1])

        if has_diseases is True:
            qs = qs.filter(diseases_count__gt=0)
        elif has_diseases is False:
            qs = qs.filter(diseases_count=0)

        if has_image is True:
            qs = qs.exclude(Q(image="") | Q(image__isnull=True))
        elif has_image is False:
            qs = qs.filter(Q(image="") | Q(image__isnull=True))

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(dosage__icontains=q))
            qs = qs.annotate(
                _rank=Case(
                    When(name__iexact=q, then=Value(0)),
                    When(name__istartswith=q, then=Value(1)),
                    When(name__icontains=q, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            ).order_by("_rank", ordering)
        else:
            qs = qs.order_by(ordering)

        if disease_id_raw or has_diseases is not None:
            qs = qs.distinct()

        page_size = _int_param(
            request,
            "page_size",
            _int_param(request, "limit", 50, min_v=1, max_v=100),
            min_v=1,
            max_v=100,
        )
        if request.query_params.get("page") is not None or request.query_params.get("offset") is None:
            page = _int_param(request, "page", 1, min_v=1, max_v=1_000_000)
            offset = (page - 1) * page_size
        else:
            try:
                offset = max(int(request.query_params.get("offset") or 0), 0)
            except (TypeError, ValueError):
                offset = 0
            page = (offset // page_size) + 1

        total = qs.count()
        rows = list(qs[offset : offset + page_size])

        if include_diseases:
            id_list = [d.id for d in rows]
            detailed = (
                _active_drugs_qs()
                .filter(id__in=id_list)
                .prefetch_related(
                    Prefetch(
                        "diseases",
                        queryset=Disease.objects.only("id", "name", "description").order_by("name"),
                    )
                )
                .annotate(diseases_count=Count("diseases", distinct=True))
            )
            by_id = {d.id: d for d in detailed}
            rows = [by_id[i] for i in id_list if i in by_id]
            data = DrugSerializer(rows, many=True, context={"request": request}).data
        else:
            for row in rows:
                if not hasattr(row, "diseases_count"):
                    row.diseases_count = 0
            data = DrugListSerializer(rows, many=True, context={"request": request}).data

        has_next = offset + page_size < total
        base = request.build_absolute_uri(request.path)

        def _page_url(p: int) -> str | None:
            if p < 1:
                return None
            params = request.query_params.copy()
            params["page"] = str(p)
            params["page_size"] = str(page_size)
            params.pop("offset", None)
            params.pop("limit", None)
            return f"{base}?{params.urlencode()}"

        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "total_pages": max((total + page_size - 1) // page_size, 1) if page_size else 1,
                "next": _page_url(page + 1) if has_next else None,
                "previous": _page_url(page - 1) if offset > 0 else None,
                "results": data,
            }
        )


class PublicDrugDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Лекарства"],
        summary="Получить лекарство",
        parameters=[
            OpenApiParameter(name="include_related", required=False, type=bool),
        ],
    )
    def get(self, request, pk: int):
        include_related = _bool_param(request, "include_related")
        if include_related is False:
            obj = get_object_or_404(_active_drugs_qs(), pk=pk)
            return Response(DrugSerializer(obj, context={"request": request, "skip_related": True}).data)

        obj = get_object_or_404(
            _active_drugs_qs().prefetch_related(
                Prefetch(
                    "diseases",
                    queryset=Disease.objects.only("id", "name", "description").order_by("name"),
                )
            ),
            pk=pk,
        )
        return Response(DrugSerializer(obj, context={"request": request}).data)
