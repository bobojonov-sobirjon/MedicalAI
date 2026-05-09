from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    Mobile only needs AI block + resolved selections.
    """
    return {
        "ai": full_result.get("ai", {}),
    }


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
            "Подбор релевантных заболеваний из локального справочника и структурированный ответ нейросети Google Gemini. "
            "Не заменяет очную консультацию врача."
        ),
        request=DiagnoseRequestSerializer,
    )
    def post(self, request):
        ser = DiagnoseRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        out = run_diagnosis(
            user=request.user,
            symptom_ids=data["symptoms"],
            symptoms_text=(data.get("symptoms_text") or "").strip(),
            body_part_ids=data.get("body_parts") or [],
            temperature_c=data.get("temperature_c"),
            blood_pressure=data.get("blood_pressure") or "",
        )
        row = AssistantDiagnosis.objects.create(
            user=request.user,
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
                "symptoms_resolved": out.get("symptoms_resolved", []),
                "body_parts_resolved": out.get("body_parts_resolved", []),
                **_public_context(out),
                **_public_result(out),
            },
            status=status.HTTP_200_OK,
        )


class MyAssistantDiagnosisListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Помощник"], summary="История помощника (мои запросы)", responses=AssistantDiagnosisSerializer(many=True))
    def get(self, request):
        qs = AssistantDiagnosis.objects.filter(user=request.user).order_by("-created_at")[:200]

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
        x = AssistantDiagnosis.objects.filter(user=request.user, pk=pk).first()
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
