from __future__ import annotations

from rest_framework import serializers


class DiagnoseRequestSerializer(serializers.Serializer):
    symptoms = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=True,
        allow_empty=False,
        help_text="Список ID симптомов из `GET /api/catalog/symptoms/?q=...`.",
    )
    symptoms_text = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=8000,
        help_text="Опционально: доп. симптомы/уточнения текстом (если нет в справочнике).",
    )
    body_parts = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
        help_text="Опционально: список ID частей тела из `GET /api/catalog/body-parts/`.",
    )
    temperature_c = serializers.FloatField(required=False, allow_null=True)
    blood_pressure = serializers.CharField(required=False, allow_blank=True, max_length=32)
    subject_user_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID профиля (вы или привязанный член семьи). По умолчанию — текущий пользователь.",
    )

    def validate_subject_user_id(self, value):
        if value in (None, ""):
            return None
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Требуется авторизация.")
        from apps.accounts.family_access import resolve_profile_user

        if resolve_profile_user(request.user, int(value)) is None:
            raise serializers.ValidationError("Недопустимый subject_user_id.")
        return int(value)


class AssistantDiagnosisSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    subject_user_id = serializers.IntegerField(allow_null=True)
    subject_user_label = serializers.CharField(allow_blank=True, required=False)
    symptom_ids = serializers.ListField(child=serializers.IntegerField(min_value=1))
    symptoms = serializers.ListField(child=serializers.JSONField(), required=False)
    symptoms_text = serializers.CharField(allow_blank=True)
    body_part_ids = serializers.ListField(child=serializers.IntegerField(min_value=1))
    body_parts = serializers.ListField(child=serializers.JSONField(), required=False)
    temperature_c = serializers.FloatField(allow_null=True)
    blood_pressure = serializers.CharField(allow_blank=True)
    result = serializers.JSONField()
    created_at = serializers.DateTimeField()
