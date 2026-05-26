from __future__ import annotations

import secrets

from rest_framework import serializers

from .family_access import family_link_for
from .models import CustomUser, FamilyLink


class ProfileCardSerializer(serializers.ModelSerializer):
    """Карточка профиля для карусели (ТЗ §7.7 / §8.2.3)."""

    avatar_url = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    link_id = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "is_owner",
            "label",
            "link_id",
            "username",
            "first_name",
            "last_name",
            "nickname",
            "gender",
            "city",
            "date_of_birth",
            "height_cm",
            "weight_kg",
            "chronic_diseases",
            "had_covid",
            "avatar_url",
        )

    def get_avatar_url(self, obj: CustomUser) -> str | None:
        request = self.context.get("request")
        from apps.core.media_urls import file_field_url

        return file_field_url(request, obj.avatar if obj.avatar else None)

    def get_is_owner(self, obj: CustomUser) -> bool:
        owner_id = self.context.get("owner_id")
        return owner_id is not None and obj.pk == owner_id

    def get_label(self, obj: CustomUser) -> str:
        labels = self.context.get("member_labels") or {}
        if obj.pk == self.context.get("owner_id"):
            return labels.get(obj.pk, "")
        return labels.get(obj.pk, "")

    def get_link_id(self, obj: CustomUser) -> int | None:
        link_ids = self.context.get("member_link_ids") or {}
        return link_ids.get(obj.pk)


class FamilyProfileCreateSerializer(serializers.Serializer):
    """Создание нового семейного профиля без отдельной регистрации (ТЗ §7.7)."""

    label = serializers.CharField(max_length=64, help_text="Подпись профиля в карусели, например «Сын».")
    first_name = serializers.CharField(max_length=150, help_text="Имя.")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    nickname = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    gender = serializers.ChoiceField(
        choices=CustomUser.Gender.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    city = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    height_cm = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=300)
    weight_kg = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=5,
        decimal_places=2,
        min_value=0,
    )
    chronic_diseases = serializers.CharField(required=False, allow_blank=True, default="")
    had_covid = serializers.BooleanField(required=False, allow_null=True)

    def create_member(self, owner: CustomUser) -> tuple[CustomUser, FamilyLink]:
        data = self.validated_data
        username = f"fam_{owner.pk}_{secrets.token_hex(8)}"
        while CustomUser.objects.filter(username=username).exists():
            username = f"fam_{owner.pk}_{secrets.token_hex(8)}"

        member = CustomUser.objects.create(
            username=username,
            first_name=data["first_name"].strip(),
            last_name=(data.get("last_name") or "").strip(),
            nickname=(data.get("nickname") or "").strip(),
            gender=data.get("gender") or "",
            city=(data.get("city") or "").strip(),
            date_of_birth=data.get("date_of_birth"),
            height_cm=data.get("height_cm"),
            weight_kg=data.get("weight_kg"),
            chronic_diseases=(data.get("chronic_diseases") or "").strip(),
            had_covid=data.get("had_covid"),
        )
        member.set_unusable_password()
        member.save(update_fields=["password"])

        link, _ = FamilyLink.objects.get_or_create(
            owner=owner,
            member=member,
            defaults={"label": data["label"].strip()},
        )
        if link.label != data["label"].strip():
            link.label = data["label"].strip()
            link.save(update_fields=["label"])
        return member, link


class FamilyMemberUpdateSerializer(serializers.Serializer):
    label = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text="Подпись связи (например «Мама»).",
    )
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    nickname = serializers.CharField(max_length=64, required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=CustomUser.Gender.choices, required=False, allow_blank=True)
    city = serializers.CharField(max_length=128, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    height_cm = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=300)
    weight_kg = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=5,
        decimal_places=2,
        min_value=0,
    )
    chronic_diseases = serializers.CharField(required=False, allow_blank=True)
    had_covid = serializers.BooleanField(required=False, allow_null=True)

    def update_link_and_member(self, owner: CustomUser, member_id: int) -> CustomUser:
        link = family_link_for(owner, member_id)
        if not link:
            raise serializers.ValidationError({"detail": "Профиль не найден или не привязан к вам."})

        data = self.validated_data
        if "label" in data:
            link.label = (data["label"] or "").strip()
            link.save(update_fields=["label"])

        member = link.member
        user_fields = (
            "first_name",
            "last_name",
            "nickname",
            "gender",
            "city",
            "date_of_birth",
            "height_cm",
            "weight_kg",
            "chronic_diseases",
            "had_covid",
        )
        update_fields: list[str] = []
        for field in user_fields:
            if field in data:
                setattr(member, field, data[field])
                update_fields.append(field)
        if update_fields:
            member.save(update_fields=update_fields)
        return member
