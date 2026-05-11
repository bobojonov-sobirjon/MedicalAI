from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import CustomUser, FamilyLink
from apps.catalog.models import Disease, Drug

from .models import DiseaseRecord, DoctorVisit, Analysis, Prescription


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "first_name", "last_name", "username")


class DoctorVisitUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorVisit
        fields = (
            "visit_date",
            "specialty",
            "doctor_full_name",
            "diagnosis",
            "medicines_text",
            "procedures_text",
        )
        extra_kwargs = {
            "visit_date": {"help_text": "Doctor visit date (YYYY-MM-DD)."},
            "specialty": {"help_text": "Doctor specialty (e.g. therapist)."},
            "doctor_full_name": {"help_text": "Doctor full name."},
            "diagnosis": {"help_text": "Diagnosis from doctor."},
            "medicines_text": {"help_text": "Medicines list (free text) including dosage if needed."},
            "procedures_text": {"help_text": "Procedures list (free text)."},
        }


class AnalysisUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = ("taken_date", "name", "result_text", "photo")
        extra_kwargs = {
            "taken_date": {"help_text": "Analysis date (YYYY-MM-DD)."},
            "name": {"help_text": "Analysis name (e.g. CBC)."},
            "result_text": {"help_text": "Analysis result (free text)."},
            "photo": {
                "help_text": "Optional photo/file. For reliable upload use PATCH /api/me/analyses/{id}/ as multipart."
            },
        }


class AnalysisUpsertInRecordSerializer(serializers.ModelSerializer):
    """
    Nested serializer for DiseaseRecord create/patch.
    Excludes `photo` so OpenAPI for DiseaseRecordUpsertSerializer stays JSON-only.
    Upload a photo via PATCH /api/me/analyses/{id}/ as multipart.
    """

    class Meta:
        model = Analysis
        fields = ("taken_date", "name", "result_text")
        extra_kwargs = {
            "taken_date": {"help_text": "Analysis date (YYYY-MM-DD)."},
            "name": {"help_text": "Analysis name (e.g. CBC)."},
            "result_text": {"help_text": "Analysis result (free text)."},
        }


class PrescriptionUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = ("photo", "note")
        extra_kwargs = {
            "photo": {
                "help_text": "Optional photo/file. For reliable upload use PATCH /api/me/prescriptions/{id}/ as multipart."
            },
            "note": {"help_text": "Optional note about prescription."},
        }


class PrescriptionUpsertInRecordSerializer(serializers.ModelSerializer):
    """
    Nested serializer for DiseaseRecord create/patch.
    Excludes `photo` so OpenAPI for DiseaseRecordUpsertSerializer stays JSON-only.
    Upload a photo via PATCH /api/me/prescriptions/{id}/ as multipart.
    """

    class Meta:
        model = Prescription
        fields = ("note",)
        extra_kwargs = {"note": {"help_text": "Optional note about prescription."}}


class DiseaseMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disease
        fields = ("id", "name")


class DrugMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Drug
        fields = ("id", "name", "dosage", "rating")


class DiseaseRecordListSerializer(serializers.ModelSerializer):
    disease = DiseaseMiniSerializer(read_only=True)
    subject_user = UserMiniSerializer(read_only=True)

    class Meta:
        model = DiseaseRecord
        fields = (
            "id",
            "date_of_illness",
            "title",
            "disease",
            "subject_user",
            "created_at",
            "updated_at",
        )


class DiseaseRecordDetailSerializer(serializers.ModelSerializer):
    disease = DiseaseMiniSerializer(read_only=True)
    subject_user = UserMiniSerializer(read_only=True)
    drugs = DrugMiniSerializer(read_only=True, many=True)
    doctor_visits = serializers.SerializerMethodField()
    analyses = serializers.SerializerMethodField()
    prescriptions = serializers.SerializerMethodField()

    class Meta:
        model = DiseaseRecord
        fields = (
            "id",
            "date_of_illness",
            "title",
            "disease",
            "subject_user",
            "symptoms",
            "drugs",
            "doctor_visits",
            "analyses",
            "prescriptions",
            "created_at",
            "updated_at",
        )

    def get_doctor_visits(self, obj):
        return DoctorVisitSerializer(obj.doctor_visits.all(), many=True, context={"request": self.context["request"]}).data

    def get_analyses(self, obj):
        return AnalysisSerializer(obj.analyses.all(), many=True, context={"request": self.context["request"]}).data

    def get_prescriptions(self, obj):
        return PrescriptionSerializer(obj.prescriptions.all(), many=True, context={"request": self.context["request"]}).data


class DiseaseRecordUpsertSerializer(serializers.ModelSerializer):
    disease_id = serializers.PrimaryKeyRelatedField(
        source="disease", queryset=Disease.objects.all(), required=False, allow_null=True
    )
    subject_user_id = serializers.PrimaryKeyRelatedField(
        source="subject_user",
        queryset=CustomUser.objects.none(),
        required=False,
        allow_null=True,
        help_text="Кому относится запись: вы или привязанный профиль. По умолчанию — вы.",
    )
    drug_ids = serializers.PrimaryKeyRelatedField(
        source="drugs", queryset=Drug.objects.all(), many=True, required=False
    )
    doctor_visits = DoctorVisitUpsertSerializer(
        many=True,
        required=False,
        help_text="Список посещений врача (если передан — заменяет текущий список).",
    )
    analyses = AnalysisUpsertInRecordSerializer(
        many=True,
        required=False,
        help_text="Список анализов (если передан — заменяет текущий список).",
    )
    prescriptions = PrescriptionUpsertInRecordSerializer(
        many=True,
        required=False,
        help_text="Список рецептов/фото (если передан — заменяет текущий список).",
    )

    class Meta:
        model = DiseaseRecord
        fields = (
            "date_of_illness",
            "title",
            "disease_id",
            "subject_user_id",
            "symptoms",
            "drug_ids",
            "doctor_visits",
            "analyses",
            "prescriptions",
        )
        extra_kwargs = {
            "date_of_illness": {"help_text": "Disease start date (YYYY-MM-DD)."},
            "title": {"help_text": "Disease title (free text)."},
            "symptoms": {"help_text": "Symptoms description (free text)."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        field = self.fields.get("subject_user_id")
        if field and request and request.user.is_authenticated:
            member_ids = list(
                FamilyLink.objects.filter(owner=request.user).values_list("member_id", flat=True)
            )
            allowed = [request.user.pk] + member_ids
            field.queryset = CustomUser.objects.filter(pk__in=allowed)

    def validate_subject_user_id(self, value: CustomUser | None):
        if value is None:
            return value
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Нет контекста пользователя.")
        u = request.user
        if value.pk == u.pk:
            return value
        if FamilyLink.objects.filter(owner=u, member=value).exists():
            return value
        raise serializers.ValidationError("Нельзя привязать эту запись к выбранному пользователю.")


class DoctorVisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorVisit
        fields = (
            "id",
            "visit_date",
            "specialty",
            "doctor_full_name",
            "diagnosis",
            "medicines_text",
            "procedures_text",
            "created_at",
            "updated_at",
        )


class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = (
            "id",
            "taken_date",
            "name",
            "result_text",
            "photo",
            "created_at",
            "updated_at",
        )


class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = ("id", "photo", "note", "created_at")


def upsert_doctor_visits(record: DiseaseRecord, items: list[dict]) -> None:
    # No manual id input in nested payloads: treat as replace-with-create.
    DoctorVisit.objects.filter(record=record).delete()
    for raw in items:
        s = DoctorVisitUpsertSerializer(data=raw)
        s.is_valid(raise_exception=True)
        DoctorVisit.objects.create(record=record, **s.validated_data)


def upsert_analyses(record: DiseaseRecord, items: list[dict]) -> None:
    # No manual id input in nested payloads: treat as replace-with-create.
    Analysis.objects.filter(record=record).delete()
    for raw in items:
        s = AnalysisUpsertInRecordSerializer(data=raw)
        s.is_valid(raise_exception=True)
        Analysis.objects.create(record=record, **s.validated_data)


def upsert_prescriptions(record: DiseaseRecord, items: list[dict]) -> None:
    # No manual id input in nested payloads: treat as replace-with-create.
    Prescription.objects.filter(record=record).delete()
    for raw in items:
        s = PrescriptionUpsertInRecordSerializer(data=raw)
        s.is_valid(raise_exception=True)
        Prescription.objects.create(record=record, **s.validated_data)

