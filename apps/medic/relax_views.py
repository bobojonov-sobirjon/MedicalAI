from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.media_urls import file_field_url

from .models import RelaxAsset

TAG = "Релакс"

VALID_CATEGORIES = ("gif", "video", "music")
DEFAULT_LIMIT = 200


def _serialize_relax_item(request, asset: RelaxAsset) -> dict:
    url = (asset.external_url or "").strip() or file_field_url(request, asset.file)
    return {
        "id": asset.id,
        "title": asset.title,
        "category": asset.category,
        "url": url or None,
        "sort_order": asset.sort_order,
    }


class RelaxFeedView(APIView):
    """ТЗ §7.21 / §5.9 — лента GIF, видео и музыки."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=[TAG],
        summary="Лента релакса",
        description=(
            "Без `category` возвращает объект с ключами `gif`, `video`, `music`. "
            "С `category` — массив элементов одной категории."
        ),
        parameters=[
            OpenApiParameter(
                name="category",
                type=str,
                required=False,
                enum=list(VALID_CATEGORIES),
                description="Фильтр: gif | video | music. Если не передан — все категории.",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                required=False,
                description=f"Лимит на категорию (по умолчанию {DEFAULT_LIMIT}, максимум 500).",
            ),
        ],
        responses={
            200: inline_serializer(
                name="RelaxFeedResponse",
                fields={
                    "gif": serializers.ListField(child=serializers.DictField()),
                    "video": serializers.ListField(child=serializers.DictField()),
                    "music": serializers.ListField(child=serializers.DictField()),
                },
            ),
        },
    )
    def get(self, request):
        limit = min(int(request.query_params.get("limit") or DEFAULT_LIMIT), 500)
        cat = (request.query_params.get("category") or "").strip().lower()

        if cat:
            if cat not in VALID_CATEGORIES:
                return Response(
                    {"detail": f"category должен быть одним из: {', '.join(VALID_CATEGORIES)}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = RelaxAsset.objects.filter(is_active=True, category=cat).order_by("sort_order", "id")[:limit]
            return Response([_serialize_relax_item(request, row) for row in qs])

        out: dict[str, list] = {}
        for category in VALID_CATEGORIES:
            qs = RelaxAsset.objects.filter(is_active=True, category=category).order_by("sort_order", "id")[:limit]
            out[category] = [_serialize_relax_item(request, row) for row in qs]
        return Response(out)
