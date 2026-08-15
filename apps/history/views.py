from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db import transaction
import httpx
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.gemini import (
    GeminiConfigError,
    format_lab_ocr_for_client,
    merge_lab_ocr_result_text,
    transcribe_lab_image,
)
from apps.core.rutronix import RuTronixConfigError

from .models import DiseaseRecord, DoctorVisit, Analysis, Prescription
from .serializers import (
    AnalysisCreateMultipartSerializer,
    AnalysisOcrFormSerializer,
    AnalysisSerializer,
    AnalysisUpsertSerializer,
    DiseaseRecordDetailSerializer,
    DiseaseRecordListSerializer,
    DiseaseRecordUpsertSerializer,
    DoctorVisitCreateMultipartSerializer,
    DoctorVisitSerializer,
    DoctorVisitUpsertSerializer,
    PrescriptionCreateMultipartSerializer,
    PrescriptionSerializer,
    PrescriptionUpsertSerializer,
)


def _q(request) -> str:
    return (request.query_params.get("q") or "").strip()


_PRESCRIPTION_MEDIA_ERR = (
    "Не удалось сохранить файл на диск. Проверьте MEDIA_ROOT в окружении и права на запись "
    "для пользователя Gunicorn (например: mkdir -p …/media/prescriptions && chown нужному пользователю)."
)


def _prescription_save_error_response(exc: BaseException) -> Response:
    if isinstance(exc, (OSError, PermissionError)):
        return Response(
            {"detail": f"{_PRESCRIPTION_MEDIA_ERR} ({exc!s})"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


_MULTIPART_PARSERS = (MultiPartParser, FormParser, JSONParser)


class MyHistoryDrugPickerView(APIView):
    """
    GET for UI «Препараты» on the history form.
    Same catalog as «Лекарства»; allowed under history_only paywall
    (path starts with /api/me/disease-records/).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["История здоровья"],
        summary="Поиск препаратов для формы истории (как раздел «Лекарства»)",
        description=(
            "Экран «Добавить запись о заболевании» → поле **Препараты**.\n\n"
            "Это **не** часть POST. Сначала GET (поиск), потом POST с `drug_ids`.\n\n"
            "- `GET ?q=Креон` — поиск (array)\n"
            "- `GET` без `q` — полный лёгкий каталог (array) для локального фильтра\n\n"
            "Тот же источник, что `GET /api/catalog/drugs/`."
        ),
        parameters=[
            OpenApiParameter(name="q", required=False, type=str, description="Поиск по названию/дозе"),
            OpenApiParameter(name="search", required=False, type=str),
            OpenApiParameter(name="name", required=False, type=str),
            OpenApiParameter(name="query", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
        ],
    )
    def get(self, request):
        from django.db.models import Case, IntegerField, Q, Value, When

        from apps.catalog.serializers import DrugPickerSerializer
        from apps.catalog.views import _active_drugs_qs, _search_query

        q = _search_query(request)
        try:
            limit = min(int(request.query_params.get("limit") or (100 if q else 50000)), 50000)
        except (TypeError, ValueError):
            limit = 100 if q else 50000

        qs = _active_drugs_qs().only("id", "name", "dosage")
        if q:
            qs = (
                qs.filter(Q(name__icontains=q) | Q(dosage__icontains=q))
                .annotate(
                    _rank=Case(
                        When(name__iexact=q, then=Value(0)),
                        When(name__istartswith=q, then=Value(1)),
                        When(name__icontains=q, then=Value(2)),
                        default=Value(3),
                        output_field=IntegerField(),
                    )
                )
                .order_by("_rank", "name")
            )
        else:
            qs = qs.order_by("name")

        rows = list(qs[:limit])
        return Response(DrugPickerSerializer(rows, many=True).data)


class MyDiseaseRecordListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    @extend_schema(
        tags=["История здоровья"],
        summary="Список моих записей о болезни",
        description="Возвращает только записи, принадлежащие текущему пользователю.",
        parameters=[
            OpenApiParameter(
                name="q",
                required=False,
                type=str,
                description="Поиск по названию / симптомам / названию заболевания.",
            ),
            OpenApiParameter(
                name="subject_user_id",
                required=False,
                type=int,
                description="Фильтр: записи для указанного профиля (вы или член семьи). Без параметра — все ваши записи.",
            ),
        ],
        responses=DiseaseRecordListSerializer(many=True),
    )
    def get(self, request):
        q = _q(request)
        qs = (
            DiseaseRecord.objects.filter(user=request.user)
            .select_related("disease", "subject_user")
            .prefetch_related("drugs", "doctor_visits", "analyses", "prescriptions")
            .order_by("-date_of_illness", "-created_at")
        )
        sid = request.query_params.get("subject_user_id")
        if sid and str(sid).isdigit():
            from apps.accounts.family_access import resolve_profile_user

            profile = resolve_profile_user(request.user, int(sid))
            if profile is None:
                return Response({"detail": "Недопустимый subject_user_id."}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(subject_user_id=profile.pk)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(symptoms__icontains=q) | Q(disease__name__icontains=q))
        # Return full cards in list view (same structure as detail).
        return Response(DiseaseRecordListSerializer(qs, many=True, context={"request": request}).data)

    @extend_schema(
        tags=["История здоровья"],
        summary="Создать запись о болезни",
        description=(
            "Экран «Добавить запись о заболевании».\n\n"
            "**Поиск в полях формы — отдельные GET (не внутри POST):**\n"
            "- Профиль → уже известные profiles API\n"
            "- Название болезни → `GET /api/catalog/diseases/?q=`\n"
            "- Препараты → `GET /api/me/disease-records/drugs/?q=Креон` "
            "(тот же каталог, что раздел «Лекарства»)\n\n"
            "Затем POST с выбранными id:\n"
            "`disease_id`, `drug_ids`, `subject_user_id`, `date_of_illness`, `symptoms`.\n\n"
            "Визиты/анализы/рецепты — отдельные endpoints после создания записи.\n"
            "Body: `multipart/form-data` или JSON."
        ),
        request={"multipart/form-data": DiseaseRecordUpsertSerializer},
        responses={201: DiseaseRecordDetailSerializer},
    )
    def post(self, request):
        s = DiseaseRecordUpsertSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            record = s.save(user=request.user)
        record = (
            DiseaseRecord.objects.select_related("disease", "subject_user")
            .prefetch_related("drugs", "doctor_visits", "analyses", "prescriptions")
            .get(pk=record.pk)
        )
        return Response(
            DiseaseRecordDetailSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MyDiseaseRecordDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    def _get_obj(self, request, pk: int) -> DiseaseRecord:
        return (
            DiseaseRecord.objects.select_related("disease")
            .prefetch_related("drugs", "doctor_visits", "analyses", "prescriptions")
            .get(pk=pk, user=request.user)
        )

    @extend_schema(
        tags=["История здоровья"],
        summary="Получить мою запись о болезни",
        description="Возвращает одну запись текущего пользователя. Включает вложенные doctor_visits/analyses/prescriptions.",
        responses=DiseaseRecordDetailSerializer,
    )
    def get(self, request, pk: int):
        record = self._get_obj(request, pk)
        return Response(DiseaseRecordDetailSerializer(record, context={"request": request}).data)

    @extend_schema(
        tags=["История здоровья"],
        summary="Обновить мою запись о болезни",
        description=(
            "Частичное обновление записи текущего пользователя.\n\n"
            "Request body: `multipart/form-data` (все поля в форме)."
        ),
        request={"multipart/form-data": DiseaseRecordUpsertSerializer},
        responses=DiseaseRecordDetailSerializer,
    )
    def patch(self, request, pk: int):
        record = self._get_obj(request, pk)
        s = DiseaseRecordUpsertSerializer(
            instance=record,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            record = s.save()
        record = self._get_obj(request, record.pk)
        return Response(DiseaseRecordDetailSerializer(record, context={"request": request}).data)

    @extend_schema(tags=["История здоровья"], summary="Удалить мою запись о болезни", description="Удаляет запись текущего пользователя.")
    def delete(self, request, pk: int):
        DiseaseRecord.objects.filter(pk=pk, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyDoctorVisitListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    @extend_schema(
        tags=["Визиты врача"],
        summary="Добавить посещение врача",
        description=(
            "Создаёт новое посещение врача.\n\n"
            "Request body: `multipart/form-data`: поле `record_id` + поля визита (как PATCH /api/auth/me/)."
        ),
        request={"multipart/form-data": DoctorVisitCreateMultipartSerializer},
        responses={201: DoctorVisitSerializer},
    )
    def post(self, request):
        s = DoctorVisitCreateMultipartSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(DoctorVisitSerializer(obj).data, status=status.HTTP_201_CREATED)


class MyDoctorVisitDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    def _get_obj(self, request, pk: int) -> DoctorVisit:
        return DoctorVisit.objects.select_related("record").get(pk=pk, record__user=request.user)

    @extend_schema(
        tags=["Визиты врача"],
        summary="Обновить посещение врача",
        description="Обновляет посещение врача (должно принадлежать текущему пользователю).",
        request={"multipart/form-data": DoctorVisitUpsertSerializer},
        responses=DoctorVisitSerializer,
    )
    def patch(self, request, pk: int):
        obj = self._get_obj(request, pk)
        s = DoctorVisitUpsertSerializer(
            instance=obj, data=request.data, partial=True, context={"request": request}
        )
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(DoctorVisitSerializer(obj).data)

    @extend_schema(tags=["Визиты врача"], summary="Удалить посещение врача", description="Удаляет посещение врача (должно принадлежать текущему пользователю).")
    def delete(self, request, pk: int):
        DoctorVisit.objects.filter(pk=pk, record__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyAnalysisListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    @extend_schema(
        tags=["Анализы"],
        summary="Добавить анализ",
        description=(
            "Создаёт новый анализ.\n\n"
            "Request body: `multipart/form-data`: `record_id` + поля анализа и опционально `photo`."
        ),
        request={"multipart/form-data": AnalysisCreateMultipartSerializer},
        responses={201: AnalysisSerializer},
    )
    def post(self, request):
        s = AnalysisCreateMultipartSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(AnalysisSerializer(obj, context={"request": request}).data, status=status.HTTP_201_CREATED)


class MyAnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    def _get_obj(self, request, pk: int) -> Analysis:
        return Analysis.objects.select_related("record").get(pk=pk, record__user=request.user)

    @extend_schema(
        tags=["Анализы"],
        summary="Обновить анализ",
        description="Обновляет анализ (должен принадлежать текущему пользователю). Для фото используйте multipart/form-data.",
        request={"multipart/form-data": AnalysisUpsertSerializer},
        responses=AnalysisSerializer,
    )
    def patch(self, request, pk: int):
        obj = self._get_obj(request, pk)
        s = AnalysisUpsertSerializer(instance=obj, data=request.data, partial=True, context={"request": request})
        s.is_valid(raise_exception=True)
        obj = s.save()
        return Response(AnalysisSerializer(obj).data)

    @extend_schema(tags=["Анализы"], summary="Удалить анализ", description="Удаляет анализ (должен принадлежать текущему пользователю).")
    def delete(self, request, pk: int):
        Analysis.objects.filter(pk=pk, record__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AnalysisOcrFormView(APIView):
    """
    OCR: все поля в теле запроса как multipart/form-data (аналог PATCH /api/auth/me/).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    @extend_schema(
        tags=["Анализы"],
        summary="OCR анализа (multipart: record_id, analysis_id, photo, mode)",
        description=(
            "Все поля в Request body как `multipart/form-data`.\n"
            "Если `photo` передан — сохраняется в анализ и сразу выполняется OCR.\n"
            "Если нет — используется уже загруженное фото анализа."
        ),
        request={"multipart/form-data": AnalysisOcrFormSerializer},
        responses={200: AnalysisSerializer},
    )
    def post(self, request):
        s = AnalysisOcrFormSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        record_id = int(s.validated_data["record_id"])
        analysis_id = int(s.validated_data["analysis_id"])
        mode_raw = s.validated_data.get("mode") or "append"
        mode = mode_raw.lower() if isinstance(mode_raw, str) else "append"

        analysis = Analysis.objects.select_related("record").get(
            pk=analysis_id, record__id=record_id, record__user=request.user
        )

        uploaded = s.validated_data.get("photo")
        if uploaded is not None:
            analysis.photo = uploaded
            analysis.save(update_fields=["photo", "updated_at"])

        if not analysis.photo:
            return Response(
                {"detail": "Сначала загрузите фото анализа (PATCH multipart) или передайте `photo` в этом запросе."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with analysis.photo.open("rb") as f:
                image_raw = f.read()
            name = (analysis.photo.name or "").lower()
            mime = "image/png" if name.endswith(".png") else "image/webp" if name.endswith(".webp") else "image/jpeg"
            try:
                text = format_lab_ocr_for_client(transcribe_lab_image(image_raw, mime))
            except (GeminiConfigError, RuTronixConfigError):
                return Response(
                    {"detail": "Не настроен RuTronix для OCR: RUTRONIX_API_KEY и RUTRONIX_VISION_MODEL."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except httpx.TimeoutException:
                return Response(
                    {
                        "detail": (
                            "Таймаут ответа RuTronix (OCR). В .env увеличьте RUTRONIX_VISION_READ_S "
                            "и/или RUTRONIX_VISION_TIMEOUT_S; на сервере — gunicorn --timeout и proxy_read_timeout."
                        )
                    },
                    status=status.HTTP_504_GATEWAY_TIMEOUT,
                )
            except Exception as exc:  # pragma: no cover
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

            analysis.result_text = merge_lab_ocr_result_text(old=analysis.result_text, new=text, mode=mode)
            analysis.save(update_fields=["result_text", "updated_at"])
            return Response(AnalysisSerializer(analysis, context={"request": request}).data)
        except Exception as exc:  # pragma: no cover
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MyPrescriptionListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    @extend_schema(
        tags=["Рецепты"],
        summary="Добавить рецепт/фото",
        description=(
            "Создаёт новый рецепт/фото.\n\n"
            "Request body: `multipart/form-data`: `record_id` + `photo` / `note`."
        ),
        request={"multipart/form-data": PrescriptionCreateMultipartSerializer},
        responses={201: PrescriptionSerializer},
    )
    def post(self, request):
        try:
            s = PrescriptionCreateMultipartSerializer(data=request.data, context={"request": request})
            s.is_valid(raise_exception=True)
            obj = s.save()
            return Response(
                PrescriptionSerializer(obj, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        except APIException:
            raise
        except Exception as exc:  # pragma: no cover
            return _prescription_save_error_response(exc)


class MyPrescriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = _MULTIPART_PARSERS

    def _get_obj(self, request, pk: int) -> Prescription:
        return Prescription.objects.select_related("record").get(pk=pk, record__user=request.user)

    @extend_schema(
        tags=["Рецепты"],
        summary="Обновить рецепт/фото",
        description="Обновляет рецепт/фото (должен принадлежать текущему пользователю). Для фото используйте multipart/form-data.",
        request={"multipart/form-data": PrescriptionUpsertSerializer},
        responses=PrescriptionSerializer,
    )
    def patch(self, request, pk: int):
        obj = self._get_obj(request, pk)
        s = PrescriptionUpsertSerializer(
            instance=obj, data=request.data, partial=True, context={"request": request}
        )
        try:
            s.is_valid(raise_exception=True)
            obj = s.save()
            return Response(PrescriptionSerializer(obj, context={"request": request}).data)
        except APIException:
            raise
        except Exception as exc:  # pragma: no cover
            return _prescription_save_error_response(exc)

    @extend_schema(tags=["Рецепты"], summary="Удалить рецепт/фото", description="Удаляет рецепт/фото (должен принадлежать текущему пользователю).")
    def delete(self, request, pk: int):
        Prescription.objects.filter(pk=pk, record__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

