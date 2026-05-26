from django.contrib import admin

from .models import BodyPart, Disease, Drug, DrugViewLog, Symptom


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ("name", "aliases")
    search_fields = ("name", "aliases")


@admin.register(BodyPart)
class BodyPartAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "sort_order")
    list_filter = ("code",)
    search_fields = ("label", "code")
    ordering = ("sort_order", "label")


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ("name", "dosage", "rating", "created_at", "updated_at")
    search_fields = ("name", "dosage")
    filter_horizontal = ("diseases",)


@admin.register(DrugViewLog)
class DrugViewLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "drug", "viewed_at")
    raw_id_fields = ("user", "drug")
    search_fields = ("user__username", "user__email", "drug__name")

