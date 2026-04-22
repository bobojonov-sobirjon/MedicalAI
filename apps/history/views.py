from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .models import DiseaseRecord, DoctorVisit, Analysis, Prescription
from .serializers import (
    DiseaseRecordListSerializer,
    DiseaseRecordDetailSerializer,
    DiseaseRecordUpsertSerializer,
    DoctorVisitSerializer,
    DoctorVisitUpsertSerializer,
    AnalysisSerializer,
    AnalysisUpsertSerializer,
    PrescriptionSerializer,
    PrescriptionUpsertSerializer,
    upsert_doctor_visits,
    upsert_analyses,
    upsert_prescriptions,
)


def _q(request) -> str:
    return (request.query_params.get("q") or "").strip()


class MyDiseaseRecordListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["My Health"],
        summary="Список моих записей о болезни",
        description="Возвращает только записи, принадлежащие текущему пользователю.",
        parameters=[
            OpenApiParameter(
                name="q",
                required=False,
                type=str,
                description="Поиск по названию / симптомам / названию заболевания.",
            )
        ],
        responses=DiseaseRecordListSerializer(many=True),
    )
    def get(self, request):
        q = _q(request)
        qs = DiseaseRecord.objects.filter(user=request.user).select_related("disease").order_by("-date_of_illness", "-created_at")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(symptoms__icontains=q) | Q(disease__name__icontains=q))
        return Response(DiseaseRecordListSerializer(qs, many=True, context={"request": request}).data)

    @extend_schema(
        tags=["My Health"],
        summary="Создать запись о болезни",
        description=(
            "Создаёт запись о болезни для текущего пользователя.\n\n"
            "ВАЖНО: `doctor_visits`, `analyses`, `prescriptions` можно передать вложенными списками.\n"
            "Если передадите эти списки — они будут сохранены внутри записи."
        ),
        request=DiseaseRecordUpsertSerializer,
        responses={201: DiseaseRecordDetailSerializer},
    )
    def post(self, request):
        s = DiseaseRecordUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            nested_visits = s.validated_data.pop("doctor_visits", None)
            nested_analyses = s.validated_data.pop("analyses", None)
            nested_prescriptions = s.validated_data.pop("prescriptions", None)

            record = s.save(user=request.user)
            if "drugs" in s.validated_data:
                record.drugs.set(s.validated_data["drugs"])

            if nested_visits is not None:
                upsert_doctor_visits(record, nested_visits)
            if nested_analyses is not None:
                upsert_analyses(record, nested_analyses)
            if nested_prescriptions is not None:
                upsert_prescriptions(record, nested_prescriptions)
        return Response(DiseaseRecordDetailSerializer(record).data, status=status.HTTP_201_CREATED)


class MyDiseaseRecordDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_obj(self, request, pk: int) -> DiseaseRecord:
        return (
            DiseaseRecord.objects.select_related("disease")
            .prefetch_related("drugs", "doctor_visits", "analyses", "prescriptions")
            .get(pk=pk, user=request.user)
        )

    @extend_schema(
        tags=["My Health"],
        summary="Получить мою запись о болезни",
        description="Возвращает одну запись текущего пользователя. Включает вложенные doctor_visits/analyses/prescriptions.",
        responses=DiseaseRecordDetailSerializer,
    )
    def get(self, request, pk: int):
        record = self._get_obj(request, pk)
        return Response(DiseaseRecordDetailSerializer(record, context={"request": request}).data)

    @extend_schema(
        tags=["My Health"],
        summary="Обновить мою запись о болезни",
        description=(
            "Частичное обновление записи текущего пользователя.\n\n"
            "Правила вложенного обновления (когда переданы списки):\n"
            "- вложенные списки (`doctor_visits`, `analyses`, `prescriptions`) заменяют текущие данные целиком\n"
            "- ручное поле `id` в nested payload не используется (обновляйте элементы через отдельные PATCH endpoints)\n"
        ),
        request=DiseaseRecordUpsertSerializer,
        responses=DiseaseRecordDetailSerializer,
    )
    def patch(self, request, pk: int):
        record = self._get_obj(request, pk)
        s = DiseaseRecordUpsertSerializer(instance=record, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            nested_visits = s.validated_data.pop("doctor_visits", None)
            nested_analyses = s.validated_data.pop("analyses", None)
            nested_prescriptions = s.validated_data.pop("prescriptions", None)

            record = s.save()
            if "drugs" in s.validated_data:
                record.drugs.set(s.validated_data["drugs"])

            if nested_visits is not None:
                upsert_doctor_visits(record, nested_visits)
            if nested_analyses is not None:
                upsert_analyses(record, nested_analyses)
            if nested_prescriptions is not None:
                upsert_prescriptions(record, nested_prescriptions)
        return Response(DiseaseRecordDetailSerializer(record).data)

    @extend_schema(tags=["My Health"], summary="Удалить мою запись о болезни", description="Удаляет запись текущего пользователя.")
    def delete(self, request, pk: int):
        DiseaseRecord.objects.filter(pk=pk, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyDoctorVisitListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_record(self, request, record_id: int) -> DiseaseRecord:
        return DiseaseRecord.objects.get(pk=record_id, user=request.user)

    @extend_schema(
        tags=["My Health Doctor Visits"],
        summary="Список посещений врача",
        description="Возвращает посещения врача для одной записи болезни (принадлежит текущему пользователю).",
        responses=DoctorVisitSerializer(many=True),
    )
    def get(self, request, record_id: int):
        record = self._get_record(request, record_id)
        qs = DoctorVisit.objects.filter(record=record).order_by("-visit_date", "-created_at")
        return Response(DoctorVisitSerializer(qs, many=True, context={"request": request}).data)

    @extend_schema(
        tags=["My Health Doctor Visits"],
        summary="Добавить посещение врача",
        description="Создаёт новое посещение врача внутри указанной записи болезни (должна принадлежать текущему пользователю).",
        request=DoctorVisitUpsertSerializer,
        responses={201: DoctorVisitSerializer},
    )
    def post(self, request, record_id: int):
        record = self._get_record(request, record_id)
        s = DoctorVisitUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = s.save(record=record)
        return Response(DoctorVisitSerializer(obj).data, status=status.HTTP_201_CREATED)


class MyDoctorVisitDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_obj(self, request, pk: int) -> DoctorVisit:
        return DoctorVisit.objects.select_related("record").get(pk=pk, record__user=request.user)

    @extend_schema(
        tags=["My Health Doctor Visits"],
        summary="Получить посещение врача",
        description="Возвращает одно посещение врача (должно принадлежать текущему пользователю).",
        responses=DoctorVisitSerializer,
    )
    def get(self, request, pk: int):
        obj = self._get_obj(request, pk)
        return Response(DoctorVisitSerializer(obj, context={"request": request}).data)

    @extend_schema(
        tags=["My Health Doctor Visits"],
        summary="Обновить посещение врача",
        description="Обновляет посещение врача (должно принадлежать текущему пользователю).",
        request=DoctorVisitUpsertSerializer,
        responses=DoctorVisitSerializer,
    )
    def patch(self, request, pk: int):
        obj = self._get_obj(request, pk)
        s = DoctorVisitUpsertSerializer(instance=obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(DoctorVisitSerializer(obj).data)

    @extend_schema(tags=["My Health Doctor Visits"], summary="Удалить посещение врача", description="Удаляет посещение врача (должно принадлежать текущему пользователю).")
    def delete(self, request, pk: int):
        DoctorVisit.objects.filter(pk=pk, record__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyAnalysisListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_record(self, request, record_id: int) -> DiseaseRecord:
        return DiseaseRecord.objects.get(pk=record_id, user=request.user)

    @extend_schema(
        tags=["My Health Analyses"],
        summary="Список анализов",
        description="Возвращает анализы для одной записи болезни (принадлежит текущему пользователю).",
        responses=AnalysisSerializer(many=True),
    )
    def get(self, request, record_id: int):
        record = self._get_record(request, record_id)
        qs = Analysis.objects.filter(record=record).order_by("-taken_date", "-created_at")
        return Response(AnalysisSerializer(qs, many=True, context={"request": request}).data)

    @extend_schema(
        tags=["My Health Analyses"],
        summary="Добавить анализ",
        description="Создаёт новый анализ внутри указанной записи болезни (должна принадлежать текущему пользователю).",
        request=AnalysisUpsertSerializer,
        responses={201: AnalysisSerializer},
    )
    def post(self, request, record_id: int):
        record = self._get_record(request, record_id)
        s = AnalysisUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = s.save(record=record)
        return Response(AnalysisSerializer(obj).data, status=status.HTTP_201_CREATED)


class MyAnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_obj(self, request, pk: int) -> Analysis:
        return Analysis.objects.select_related("record").get(pk=pk, record__user=request.user)

    @extend_schema(
        tags=["My Health Analyses"],
        summary="Получить анализ",
        description="Возвращает один анализ (должен принадлежать текущему пользователю).",
        responses=AnalysisSerializer,
    )
    def get(self, request, pk: int):
        obj = self._get_obj(request, pk)
        return Response(AnalysisSerializer(obj, context={"request": request}).data)

    @extend_schema(
        tags=["My Health Analyses"],
        summary="Обновить анализ",
        description="Обновляет анализ (должен принадлежать текущему пользователю). Для фото используйте multipart/form-data.",
        request=AnalysisUpsertSerializer,
        responses=AnalysisSerializer,
    )
    def patch(self, request, pk: int):
        obj = self._get_obj(request, pk)
        s = AnalysisUpsertSerializer(instance=obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(AnalysisSerializer(obj).data)

    @extend_schema(tags=["My Health Analyses"], summary="Удалить анализ", description="Удаляет анализ (должен принадлежать текущему пользователю).")
    def delete(self, request, pk: int):
        Analysis.objects.filter(pk=pk, record__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyPrescriptionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_record(self, request, record_id: int) -> DiseaseRecord:
        return DiseaseRecord.objects.get(pk=record_id, user=request.user)

    @extend_schema(
        tags=["My Health Prescriptions"],
        summary="Список рецептов",
        description="Возвращает рецепты/фото для одной записи болезни (принадлежит текущему пользователю).",
        responses=PrescriptionSerializer(many=True),
    )
    def get(self, request, record_id: int):
        record = self._get_record(request, record_id)
        qs = Prescription.objects.filter(record=record).order_by("-created_at")
        return Response(PrescriptionSerializer(qs, many=True, context={"request": request}).data)

    @extend_schema(
        tags=["My Health Prescriptions"],
        summary="Добавить рецепт/фото",
        description="Создаёт новый рецепт/фото внутри указанной записи болезни (должна принадлежать текущему пользователю).",
        request=PrescriptionUpsertSerializer,
        responses={201: PrescriptionSerializer},
    )
    def post(self, request, record_id: int):
        record = self._get_record(request, record_id)
        s = PrescriptionUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = s.save(record=record)
        return Response(PrescriptionSerializer(obj).data, status=status.HTTP_201_CREATED)


class MyPrescriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_obj(self, request, pk: int) -> Prescription:
        return Prescription.objects.select_related("record").get(pk=pk, record__user=request.user)

    @extend_schema(
        tags=["My Health Prescriptions"],
        summary="Получить рецепт/фото",
        description="Возвращает один рецепт/фото (должен принадлежать текущему пользователю).",
        responses=PrescriptionSerializer,
    )
    def get(self, request, pk: int):
        obj = self._get_obj(request, pk)
        return Response(PrescriptionSerializer(obj, context={"request": request}).data)

    @extend_schema(
        tags=["My Health Prescriptions"],
        summary="Обновить рецепт/фото",
        description="Обновляет рецепт/фото (должен принадлежать текущему пользователю). Для фото используйте multipart/form-data.",
        request=PrescriptionUpsertSerializer,
        responses=PrescriptionSerializer,
    )
    def patch(self, request, pk: int):
        obj = self._get_obj(request, pk)
        s = PrescriptionUpsertSerializer(instance=obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(PrescriptionSerializer(obj).data)

    @extend_schema(tags=["My Health Prescriptions"], summary="Удалить рецепт/фото", description="Удаляет рецепт/фото (должен принадлежать текущему пользователю).")
    def delete(self, request, pk: int):
        Prescription.objects.filter(pk=pk, record__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

