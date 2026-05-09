from django.contrib import admin

from .models import CabinetItem


@admin.register(CabinetItem)
class CabinetItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "drug", "custom_name", "expires_at", "created_at")
    list_filter = ("expires_at",)
    search_fields = ("custom_name", "user__username", "user__email", "drug__name")
    raw_id_fields = ("user", "drug")
