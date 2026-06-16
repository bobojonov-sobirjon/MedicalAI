from django.contrib import admin

from .models import Payment, TariffPlan, UserBillingProfile, UserSubscription


@admin.register(TariffPlan)
class TariffPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "tier", "price_rub", "validity_days", "is_active", "is_purchasable", "is_auto_trial")
    list_filter = ("tier", "is_active", "is_purchasable", "is_auto_trial")
    search_fields = ("title", "slug")
    ordering = ("sort_order", "id")


@admin.register(UserBillingProfile)
class UserBillingProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "free_trial_used", "updated_at")
    list_filter = ("free_trial_used",)
    search_fields = ("user__username", "user__email", "user__phone_number")
    raw_id_fields = ("user",)


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "tariff", "status", "source", "started_at", "expires_at")
    list_filter = ("status", "source", "tariff")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user", "payment")
    date_hierarchy = "started_at"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tariff", "amount_rub", "status", "robokassa_inv_id", "paid_at", "created_at")
    list_filter = ("status", "tariff")
    search_fields = ("user__username", "robokassa_inv_id")
    raw_id_fields = ("user",)
    readonly_fields = ("callback_payload", "created_at", "updated_at")
