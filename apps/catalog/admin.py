from django.contrib import admin

from .models import BodyPart, Disease, Drug, DrugViewLog, Symptom


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    fields = ("name", "description", "instructions", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


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
    list_display = ("name", "is_active", "dosage", "rating", "updated_at")
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("name", "dosage")
    filter_horizontal = ("diseases",)
    actions = ("make_active", "make_inactive")

    @admin.action(description="Показывать в приложении (is_active=True)")
    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Показано препаратов: {updated}")

    @admin.action(description="Скрыть из приложения (is_active=False)")
    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Скрыто препаратов: {updated}")


@admin.register(DrugViewLog)
class DrugViewLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "drug", "viewed_at")
    raw_id_fields = ("user", "drug")
    search_fields = ("user__username", "user__email", "drug__name")

