from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Survey, SurveyResponse

User = get_user_model()
TAG = "Опросы"

_PROFILE_SYNC_WHITELIST = frozenset({"had_covid"})


def _serialize_survey(survey: Survey, response: SurveyResponse | None) -> dict:
    return {
        "slug": survey.slug,
        "title": survey.title,
        "question": survey.question_text,
        "answer_type": survey.answer_type,
        "choices": survey.choices or [],
        "answered": response is not None,
        "my_answer": response.answers if response else None,
        "answered_at": response.created_at.isoformat() if response else None,
    }


def _normalize_answer_payload(survey: Survey, answers) -> dict:
    if isinstance(answers, bool):
        return {"value": answers}
    if not isinstance(answers, dict):
        raise serializers.ValidationError({"answers": "Ожидается объект JSON, например {\"value\": true}."})
    if "value" not in answers:
        raise serializers.ValidationError({"answers": "Укажите ключ value (ответ на вопрос)."})
    value = answers["value"]
    if survey.answer_type == Survey.AnswerType.YES_NO:
        if not isinstance(value, bool):
            raise serializers.ValidationError({"answers": "Для yes_no передайте {\"value\": true} или false."})
    elif survey.answer_type == Survey.AnswerType.TEXT:
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError({"answers": "Укажите непустой текст в value."})
        return {"value": value.strip()}
    elif survey.answer_type == Survey.AnswerType.CHOICE:
        if value not in (survey.choices or []):
            raise serializers.ValidationError(
                {"answers": f"value должно быть одним из: {survey.choices or []}"}
            )
    return {"value": value}


def _sync_profile_field(user: User, survey: Survey, answers: dict) -> None:
    field = (survey.profile_field or "").strip()
    if not field or field not in _PROFILE_SYNC_WHITELIST:
        return
    value = answers.get("value")
    if field == "had_covid" and isinstance(value, bool):
        user.had_covid = value
        user.save(update_fields=["had_covid"])


class SurveyListView(APIView):
    """Активные опросы из админки + статус ответа текущего пользователя."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[TAG],
        summary="Список опросов",
        description=(
            "Возвращает активные опросы (вопросы из админки). "
            "Для каждого — отвечал ли уже пользователь и его ответ."
        ),
    )
    def get(self, request):
        surveys = list(Survey.objects.filter(is_active=True).order_by("sort_order", "id"))
        if not surveys:
            return Response([])
        responses = {
            r.survey_id: r
            for r in SurveyResponse.objects.filter(user=request.user, survey__in=surveys).select_related("survey")
        }
        return Response([_serialize_survey(s, responses.get(s.id)) for s in surveys])


class SurveyAnswerSubmitSerializer(serializers.Serializer):
    answers = serializers.JSONField(help_text='Ответ, напр. {"value": true} для Да/Нет.')
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class SurveyAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[TAG],
        summary="Отправить ответ на опрос",
        description="Код опроса в URL (`slug` из админки). Повторная отправка того же опроса — 409.",
        request=SurveyAnswerSubmitSerializer,
        responses={
            201: inline_serializer(
                name="SurveyAnswerCreated",
                fields={
                    "id": serializers.IntegerField(),
                    "slug": serializers.CharField(),
                    "ok": serializers.BooleanField(),
                },
            ),
            409: inline_serializer(
                name="SurveyAlreadyAnswered",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def post(self, request, slug: str):
        survey = get_object_or_404(Survey, slug=slug, is_active=True)
        if SurveyResponse.objects.filter(user=request.user, survey=survey).exists():
            return Response(
                {"detail": "Вы уже отвечали на этот опрос."},
                status=status.HTTP_409_CONFLICT,
            )
        s = SurveyAnswerSubmitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            normalized = _normalize_answer_payload(survey, s.validated_data["answers"])
        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        row = SurveyResponse.objects.create(
            user=request.user,
            survey=survey,
            answers=normalized,
            comment=(s.validated_data.get("comment") or "").strip(),
        )
        _sync_profile_field(request.user, survey, normalized)
        return Response({"id": row.id, "slug": survey.slug, "ok": True}, status=status.HTTP_201_CREATED)
