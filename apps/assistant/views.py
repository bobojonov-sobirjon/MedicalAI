from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.family_access import resolve_profile_user
from apps.accounts.models import FamilyLink
from apps.catalog.models import BodyPart, Symptom

from .models import AssistantDiagnosis
from .serializers import AssistantDiagnosisSerializer, DiagnoseRequestSerializer
from .services import run_diagnosis


def _resolve_ordered(ids: list[int], by_id: dict[int, dict]) -> list[dict]:
    out: list[dict] = []
    for i in ids or []:
        try:
            ii = int(i)
        except (TypeError, ValueError):
            continue
        obj = by_id.get(ii)
        if obj:
            out.append(obj)
    return out


def _public_result(full_result: dict) -> dict:
    """
    Trim internal helper fields from run_diagnosis output.
    Flutter Variant 1: answer + disclaimer + sources.
    possible_conditions — always list[str] (never Map dumps).
    """
    from .services import format_possible_conditions

    ai = dict(full_result.get("ai") or {})
    raw_conditions = full_result.get("possible_conditions")
    if raw_conditions is None:
        raw_conditions = ai.get("possible_conditions") or []
    conditions_text = format_possible_conditions(raw_conditions, limit=8)
    # If already strings, format_possible_conditions keeps them.
    if not conditions_text and isinstance(raw_conditions, list):
        conditions_text = [str(x).strip() for x in raw_conditions if str(x).strip()][:8]

    ai["possible_conditions"] = conditions_text
    return {
        "answer": full_result.get("answer") or ai.get("answer") or "",
        "disclaimer": full_result.get("disclaimer") or ai.get("disclaimer") or "",
        "sources": full_result.get("sources") or ai.get("sources") or [],
        "possible_conditions": conditions_text,
        "ai": ai,
    }


def _subject_payload(row: AssistantDiagnosis) -> dict:
    subj = row.subject_user
    if not subj:
        return {"subject_user_id": None, "subject_user_label": ""}
    label = ""
    if row.user_id != subj.pk:
        link = FamilyLink.objects.filter(owner_id=row.user_id, member_id=subj.pk).first()
        label = (link.label if link else "") or subj.get_full_name() or subj.username
    return {"subject_user_id": subj.pk, "subject_user_label": label}


def _public_context(full_result: dict) -> dict:
    """
    Context that is useful for the UI (and fallback when AI is unavailable).
    """
    return {
        "catalog_candidates": full_result.get("catalog_candidates", []),
        "catalog_matched": full_result.get("catalog_matched", []),
        "faq_hits": full_result.get("faq_hits", []),
    }


class DiagnoseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Помощник"],
        summary="Диагностическая подсказка по симптомам (справочник + ИИ)",
        description=(
            "Подбор заболеваний по симптомам + ИИ-ответ. "
            "Flutter: используйте поля `answer`, `disclaimer`, `sources` (Variant 1). "
            "Не заменяет очную консультацию врача."
        ),
        request=DiagnoseRequestSerializer,
        responses={
            200: inline_serializer(
                name="DiagnoseMedicalResponse",
                fields={
                    "diagnosis_id": serializers.IntegerField(),
                    "answer": serializers.CharField(),
                    "disclaimer": serializers.CharField(),
                    "sources": serializers.ListField(child=serializers.DictField()),
                },
            ),
        },
    )
    def post(self, request):
        ser = DiagnoseRequestSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        subject_id = data.get("subject_user_id")
        profile_user = resolve_profile_user(request.user, subject_id) or request.user
        out = run_diagnosis(
            user=request.user,
            profile_user=profile_user,
            symptom_ids=data["symptoms"],
            symptoms_text=(data.get("symptoms_text") or "").strip(),
            body_part_ids=data.get("body_parts") or [],
            temperature_c=data.get("temperature_c"),
            blood_pressure=data.get("blood_pressure") or "",
        )
        row = AssistantDiagnosis.objects.create(
            user=request.user,
            subject_user=profile_user,
            symptom_ids=data["symptoms"],
            symptoms_text=(data.get("symptoms_text") or "").strip(),
            body_part_ids=data.get("body_parts") or [],
            temperature_c=data.get("temperature_c"),
            blood_pressure=data.get("blood_pressure") or "",
            result=out,
        )
        return Response(
            {
                "diagnosis_id": row.id,
                **_subject_payload(row),
                "symptoms_resolved": out.get("symptoms_resolved", []),
                "body_parts_resolved": out.get("body_parts_resolved", []),
                **_public_context(out),
                **_public_result(out),
            },
            status=status.HTTP_200_OK,
        )


class MyAssistantDiagnosisListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Помощник"],
        summary="История помощника (мои запросы)",
        parameters=[
            OpenApiParameter(
                name="subject_user_id",
                type=int,
                required=False,
                description="Фильтр по профилю, для которого делалась диагностика.",
            ),
        ],
        responses=AssistantDiagnosisSerializer(many=True),
    )
    def get(self, request):
        qs = AssistantDiagnosis.objects.filter(user=request.user).select_related("subject_user").order_by("-created_at")
        sid = request.query_params.get("subject_user_id")
        if sid and str(sid).isdigit():
            qs = qs.filter(subject_user_id=int(sid))
        qs = qs[:200]

        all_symptom_ids: set[int] = set()
        all_body_part_ids: set[int] = set()
        rows = list(qs)
        for x in rows:
            all_symptom_ids.update([int(i) for i in (x.symptom_ids or []) if str(i).isdigit()])
            all_body_part_ids.update([int(i) for i in (x.body_part_ids or []) if str(i).isdigit()])

        symptoms_by_id = {
            s.id: {"id": s.id, "name": s.name, "aliases": s.aliases}
            for s in Symptom.objects.filter(id__in=all_symptom_ids)
        }
        body_parts_by_id = {
            b.id: {"id": b.id, "code": b.code, "label": b.label}
            for b in BodyPart.objects.filter(id__in=all_body_part_ids)
        }

        return Response(
            [
                {
                    "id": x.id,
                    **_subject_payload(x),
                    "symptom_ids": x.symptom_ids,
                    "symptoms": _resolve_ordered(x.symptom_ids or [], symptoms_by_id),
                    "symptoms_text": x.symptoms_text,
                    "body_part_ids": x.body_part_ids,
                    "body_parts": _resolve_ordered(x.body_part_ids or [], body_parts_by_id),
                    "temperature_c": x.temperature_c,
                    "blood_pressure": x.blood_pressure,
                    "symptoms_resolved": (x.result or {}).get("symptoms_resolved", []),
                    "body_parts_resolved": (x.result or {}).get("body_parts_resolved", []),
                    **_public_context(x.result or {}),
                    "result": _public_result(x.result or {}),
                    "created_at": x.created_at,
                }
                for x in rows
            ]
        )


class MyAssistantDiagnosisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Помощник"], summary="Получить один результат помощника", responses=AssistantDiagnosisSerializer)
    def get(self, request, pk: int):
        x = AssistantDiagnosis.objects.filter(user=request.user, pk=pk).select_related("subject_user").first()
        if not x:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)

        symptoms_by_id = {
            s.id: {"id": s.id, "name": s.name, "aliases": s.aliases}
            for s in Symptom.objects.filter(id__in=[int(i) for i in (x.symptom_ids or []) if str(i).isdigit()])
        }
        body_parts_by_id = {
            b.id: {"id": b.id, "code": b.code, "label": b.label}
            for b in BodyPart.objects.filter(id__in=[int(i) for i in (x.body_part_ids or []) if str(i).isdigit()])
        }

        return Response(
            {
                "id": x.id,
                **_subject_payload(x),
                "symptom_ids": x.symptom_ids,
                "symptoms": _resolve_ordered(x.symptom_ids or [], symptoms_by_id),
                "symptoms_text": x.symptoms_text,
                "body_part_ids": x.body_part_ids,
                "body_parts": _resolve_ordered(x.body_part_ids or [], body_parts_by_id),
                "temperature_c": x.temperature_c,
                "blood_pressure": x.blood_pressure,
                "symptoms_resolved": (x.result or {}).get("symptoms_resolved", []),
                "body_parts_resolved": (x.result or {}).get("body_parts_resolved", []),
                **_public_context(x.result or {}),
                "result": _public_result(x.result or {}),
                "created_at": x.created_at,
            }
        )
