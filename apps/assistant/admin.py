from django.contrib import admin

from .models import AssistantDiagnosis


@admin.register(AssistantDiagnosis)
class AssistantDiagnosisAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject_user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email", "symptoms_text")
    raw_id_fields = ("user", "subject_user")
    readonly_fields = ("symptom_ids", "body_part_ids", "result", "created_at")
