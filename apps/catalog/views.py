from __future__ import annotations

from django.db.models import Case, Count, IntegerField, Prefetch, Q, Value, When
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
    """Accept both `q` and `search` (history autocomplete uses either)."""
    return _query_param(request, "q") or _query_param(request, "search")


class PublicDiseaseListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Заболевания"],
        summary="Список заболеваний",
        parameters=[
            OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию"),
            OpenApiParameter(name="search", required=False, type=str, description="Алиас для q (история болезней)"),
            OpenApiParameter(name="limit", required=False, type=int, description="Лимит (по умолчанию 40 при поиске)"),
        ],
    )
    def get(self, request):
        q = _search_query(request)
        # Autocomplete for «История болезней»: light payload, name-first search.
        try:
            default_limit = 40 if q else 200
            limit = min(int(request.query_params.get("limit") or default_limit), 500)
        except (TypeError, ValueError):
            limit = 40 if q else 200

        # Only fields needed for list/autocomplete — avoid shipping huge MKB texts.
        qs = Disease.objects.all().only("id", "name", "description", "created_at", "updated_at").order_by("name")

        if q:
            # Primary: name match (Панкреатит and friends). Description only as soft fallback.
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

        rows = list(qs[:limit])
        return Response(DiseaseSerializer(rows, many=True, context={"request": request}).data)


class PublicDiseaseDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Заболевания"], summary="Получить заболевание (с лекарствами)")
    def get(self, request, pk: int):
        obj = get_object_or_404(
            Disease.objects.prefetch_related(
                Prefetch(
                    "drugs",
                    queryset=Drug.objects.filter(is_active=True)
                    .only("id", "name", "description", "instructions", "dosage", "image", "rating", "is_active")
                    .prefetch_related(
                        Prefetch(
                            "diseases",
                            queryset=Disease.objects.only("id", "name", "description").order_by("name"),
                        )
                    )
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
        qs = Symptom.objects.all().only("id", "name", "aliases", "created_at", "updated_at").order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(aliases__icontains=q))[:40]
        else:
            qs = qs[:200]
        return Response(SymptomSerializer(qs, many=True).data)


@method_decorator(cache_page(60 * 30), name="dispatch")
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
        summary="Список лекарств (pagination + filters)",
        parameters=[
            OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию / дозировке"),
            OpenApiParameter(name="page", required=False, type=int, description="Номер страницы (с 1), по умолчанию 1"),
            OpenApiParameter(name="page_size", required=False, type=int, description="Размер страницы (1–100), по умолчанию 50"),
            OpenApiParameter(name="limit", required=False, type=int, description="Альтернатива page_size (LimitOffset)"),
            OpenApiParameter(name="offset", required=False, type=int, description="Смещение (если без page)"),
            OpenApiParameter(name="disease_id", required=False, type=int, description="Только препараты, связанные с болезнью"),
            OpenApiParameter(name="letter", required=False, type=str, description="Первая буква названия (А, Б, В…)"),
            OpenApiParameter(
                name="ordering",
                required=False,
                type=str,
                description="Сортировка: name | -name | rating | -rating | created_at | -created_at",
            ),
            OpenApiParameter(
                name="has_diseases",
                required=False,
                type=bool,
                description="true — только с болезнями; false — без болезней",
            ),
            OpenApiParameter(
                name="has_image",
                required=False,
                type=bool,
                description="true — только с картинкой; false — без картинки",
            ),
            OpenApiParameter(
                name="include_diseases",
                required=False,
                type=bool,
                description="true — вложить diseases (тяжёлый ответ). По умолчанию false.",
            ),
        ],
    )
    def get(self, request):
        q = _search_query(request)
        letter = _query_param(request, "letter")
        ordering = _query_param(request, "ordering") or "name"
        disease_id_raw = _query_param(request, "disease_id")
        has_diseases = _bool_param(request, "has_diseases")
        has_image = _bool_param(request, "has_image")
        include_diseases = _bool_param(request, "include_diseases") is True

        allowed_ordering = {
            "name",
            "-name",
            "rating",
            "-rating",
            "created_at",
            "-created_at",
        }
        if ordering not in allowed_ordering:
            ordering = "name"

        # Light list queryset: defer huge text fields unless include_diseases.
        qs = Drug.objects.filter(is_active=True).defer("instructions")

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
            # IMPORTANT: do NOT icontains on huge TextField (description/instructions) —
            # that caused list hang/timeout on 13k+ drugs.
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
                Drug.objects.filter(id__in=id_list)
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
            # Attach diseases_count=0 annotation fallback for serializer if missing.
            for row in rows:
                if not hasattr(row, "diseases_count"):
                    row.diseases_count = 0
            data = DrugListSerializer(rows, many=True, context={"request": request}).data

        has_next = offset + page_size < total
        has_prev = offset > 0
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
                "previous": _page_url(page - 1) if has_prev else None,
                "results": data,
            }
        )


class PublicDrugDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Лекарства"],
        summary="Получить лекарство",
        parameters=[
            OpenApiParameter(
                name="include_related",
                required=False,
                type=bool,
                description="false — без nested diseases/drugs (быстрый режим). По умолчанию true, но с лимитами.",
            ),
        ],
    )
    def get(self, request, pk: int):
        include_related = _bool_param(request, "include_related")
        if include_related is False:
            obj = get_object_or_404(Drug.objects.filter(is_active=True), pk=pk)
            data = DrugSerializer(obj, context={"request": request, "skip_related": True}).data
            return Response(data)

        # Cap nested depth to avoid hang: serializer limits diseases and nested drugs.
        obj = get_object_or_404(
            Drug.objects.filter(is_active=True).prefetch_related(
                Prefetch(
                    "diseases",
                    queryset=Disease.objects.only("id", "name", "description").order_by("name"),
                )
            ),
            pk=pk,
        )
        return Response(DrugSerializer(obj, context={"request": request}).data)
