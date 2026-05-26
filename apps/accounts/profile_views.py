from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model

from .family_access import family_link_for
from .family_serializers import (
    FamilyMemberUpdateSerializer,
    FamilyProfileCreateSerializer,
    ProfileCardSerializer,
)
from .models import FamilyLink

User = get_user_model()

TAG = "Профили"


def _profile_list_context(request, owner):
    links = list(FamilyLink.objects.filter(owner=owner).select_related("member"))
    member_labels = {owner.pk: ""}
    member_link_ids = {}
    for link in links:
        member_labels[link.member_id] = link.label
        member_link_ids[link.member_id] = link.id
    profiles = [owner] + [link.member for link in links]
    return {
        "request": request,
        "owner_id": owner.pk,
        "member_labels": member_labels,
        "member_link_ids": member_link_ids,
    }, profiles


class ProfileListView(APIView):
    """ТЗ §7.7 — карусель: вы + дополнительные профили."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[TAG],
        summary="Список профилей",
        description="Для карусели на экране профиля. Первый элемент — владелец аккаунта (`is_owner: true`).",
        responses=ProfileCardSerializer(many=True),
    )
    def get(self, request):
        ctx, profiles = _profile_list_context(request, request.user)
        data = ProfileCardSerializer(profiles, many=True, context=ctx).data
        return Response({"profiles": data, "count": len(data)})

    @extend_schema(
        tags=[TAG],
        summary="Добавить профиль",
        description=(
            "ТЗ §7.7 — новый профиль без отдельного логина (например, пожилой родитель). "
            "Управление только через владельца аккаунта."
        ),
        request=FamilyProfileCreateSerializer,
        responses={201: ProfileCardSerializer},
    )
    def post(self, request):
        ser = FamilyProfileCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        member, _link = ser.create_member(request.user)
        ctx, _ = _profile_list_context(request, request.user)
        return Response(
            ProfileCardSerializer(member, context=ctx).data,
            status=status.HTTP_201_CREATED,
        )


class ProfileDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[TAG],
        summary="Карточка профиля",
        parameters=[
            OpenApiParameter(
                name="profile_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID пользователя (доп. профиля, не владельца).",
            ),
        ],
        responses={200: ProfileCardSerializer},
    )
    def get(self, request, profile_id: int):
        link = family_link_for(request.user, profile_id)
        if not link:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        ctx, _ = _profile_list_context(request, request.user)
        return Response(ProfileCardSerializer(link.member, context=ctx).data)

    @extend_schema(
        tags=[TAG],
        summary="Обновить профиль (PUT)",
        request=FamilyMemberUpdateSerializer,
        responses={200: ProfileCardSerializer},
    )
    def put(self, request, profile_id: int):
        return self._update(request, profile_id)

    @extend_schema(
        tags=[TAG],
        summary="Частично обновить профиль (PATCH)",
        request=FamilyMemberUpdateSerializer,
        responses={200: ProfileCardSerializer},
    )
    def patch(self, request, profile_id: int):
        return self._update(request, profile_id)

    def _update(self, request, profile_id: int):
        ser = FamilyMemberUpdateSerializer(data=request.data, partial=request.method == "PATCH")
        ser.is_valid(raise_exception=True)
        try:
            member = ser.update_link_and_member(request.user, profile_id)
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        ctx, _ = _profile_list_context(request, request.user)
        return Response(ProfileCardSerializer(member, context=ctx).data)

    @extend_schema(
        tags=[TAG],
        summary="Удалить дополнительный профиль",
        description="Удаляет связь и доп. учётную запись из вашего списка (ТЗ §7.7).",
        parameters=[
            OpenApiParameter(
                name="profile_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
            ),
        ],
        responses={204: None},
    )
    def delete(self, request, profile_id: int):
        deleted, _ = FamilyLink.objects.filter(owner=request.user, member_id=profile_id).delete()
        if not deleted:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
