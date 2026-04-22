from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.models import Site

from .models import CustomUser, PasswordResetCode, SocialAccount


# Hide built-in models we don't use in this project UI
admin.site.unregister(Group)
admin.site.unregister(Site)


class SocialAccountInline(admin.TabularInline):
    model = SocialAccount
    extra = 0
    can_delete = False
    fields = ("provider", "provider_user_id", "created_at")
    readonly_fields = ("provider", "provider_user_id", "created_at")
    show_change_link = False


class PasswordResetCodeInline(admin.TabularInline):
    model = PasswordResetCode
    extra = 0
    can_delete = False
    fields = ("used", "expires_at", "created_at")
    readonly_fields = ("used", "expires_at", "created_at")
    show_change_link = False


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Profile",
            {
                "fields": (
                    "phone_number",
                    "avatar",
                    "nickname",
                    "gender",
                    "city",
                    "date_of_birth",
                    "height_cm",
                    "weight_kg",
                ),
            },
        ),
    )
    list_display = ("username", "email", "phone_number", "nickname", "is_staff", "is_active", "date_joined")
    search_fields = ("username", "email", "phone_number")
    inlines = (SocialAccountInline, PasswordResetCodeInline)


# SocialAccount and PasswordResetCode are managed via CustomUser inline.
