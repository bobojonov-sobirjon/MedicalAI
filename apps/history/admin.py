from django.contrib import admin

from .models import DiseaseRecord, DoctorVisit, Analysis, Prescription


class DoctorVisitInline(admin.TabularInline):
    model = DoctorVisit
    extra = 0
    fields = (
        "visit_date",
        "specialty",
        "doctor_full_name",
        "diagnosis",
        "medicines_text",
        "procedures_text",
    )


class AnalysisInline(admin.TabularInline):
    model = Analysis
    extra = 0
    fields = ("taken_date", "name", "result_text", "photo")


class PrescriptionInline(admin.TabularInline):
    model = Prescription
    extra = 0
    fields = ("photo", "note")


@admin.register(DiseaseRecord)
class DiseaseRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "date_of_illness", "disease", "title", "created_at")
    search_fields = ("user__username", "user__email", "title", "symptoms", "disease__name")
    list_filter = ("date_of_illness", "created_at")
    autocomplete_fields = ("user", "disease", "drugs")
    inlines = (DoctorVisitInline, AnalysisInline, PrescriptionInline)


@admin.register(DoctorVisit)
class DoctorVisitAdmin(admin.ModelAdmin):
    list_display = ("record", "visit_date", "specialty", "doctor_full_name", "created_at")
    search_fields = ("record__user__username", "record__user__email", "specialty", "doctor_full_name", "diagnosis")
    list_filter = ("visit_date",)
    autocomplete_fields = ("record",)


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("record", "taken_date", "name", "created_at")
    search_fields = ("record__user__username", "record__user__email", "name", "result_text")
    list_filter = ("taken_date",)
    autocomplete_fields = ("record",)


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("record", "created_at")
    search_fields = ("record__user__username", "record__user__email", "note")
    autocomplete_fields = ("record",)

