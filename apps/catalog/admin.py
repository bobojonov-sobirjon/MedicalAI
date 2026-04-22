from django.contrib import admin

from .models import Disease, Drug


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ("name", "dosage", "rating", "created_at", "updated_at")
    search_fields = ("name", "dosage")
    filter_horizontal = ("diseases",)

