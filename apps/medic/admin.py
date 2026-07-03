from django.contrib import admin

from .models import (
    ApiErrorLog,
    AppUpdateBroadcast,
    AuditLogEntry,
    ChatMessage,
    ChatThread,
    City,
    DiscussionPost,
    DiseaseTipSubscription,
    DrugAnalog,
    DrugDiscussionThread,
    DrugReview,
    DrugUserStarRating,
    FaqItem,
    FeedbackTicket,
    MedicalFacility,
    NotificationEvent,
    PsychologyInquiry,
    RelaxAsset,
    SearchQueryLog,
    StaticPage,
    Survey,
    SurveyResponse,
    UsefulTip,
    UserTipSettings,
)


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "geo_level", "sort_order")
    list_filter = ("geo_level",)
    search_fields = ("name",)


@admin.register(MedicalFacility)
class MedicalFacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "city", "phone", "is_active")
    list_filter = ("kind", "city", "is_active")
    search_fields = ("name", "address", "description")
    fields = (
        "kind",
        "city",
        "name",
        "address",
        "phone",
        "hours_text",
        "description",
        "image",
        "latitude",
        "longitude",
        "external_source",
        "external_id",
        "is_active",
    )


@admin.register(UsefulTip)
class UsefulTipAdmin(admin.ModelAdmin):
    list_display = ("title", "disease", "is_active", "sort_order")
    list_filter = ("is_active",)


@admin.register(AppUpdateBroadcast)
class AppUpdateBroadcastAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at")


@admin.register(UserTipSettings)
class UserTipSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "tips_per_day", "useful_subscribed")


@admin.register(DiseaseTipSubscription)
class DiseaseTipSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "disease", "is_active")


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "title", "read_at", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "body")


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "is_active")


@admin.register(FeedbackTicket)
class FeedbackTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "subject", "created_at")


@admin.register(PsychologyInquiry)
class PsychologyInquiryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "created_at")


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "status", "updated_at")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "thread", "sender", "is_staff", "created_at")


@admin.register(DrugReview)
class DrugReviewAdmin(admin.ModelAdmin):
    list_display = ("drug", "user", "rating", "status", "created_at")
    list_filter = ("status",)
    actions = ("approve_reviews", "reject_reviews")

    def changelist_view(self, request, extra_context=None):
        pending = DrugReview.objects.filter(status=DrugReview.Status.PENDING).count()
        if pending:
            self.message_user(request, f"Новых отзывов на модерации: {pending}.", level="warning")
        return super().changelist_view(request, extra_context=extra_context)

    @admin.action(description="Одобрить выбранные отзывы")
    def approve_reviews(self, request, queryset):
        queryset.update(status=DrugReview.Status.APPROVED, reject_reason="")

    @admin.action(description="Отклонить выбранные отзывы")
    def reject_reviews(self, request, queryset):
        queryset.update(status=DrugReview.Status.REJECTED, reject_reason="Отклонено администратором")


@admin.register(DrugUserStarRating)
class DrugUserStarRatingAdmin(admin.ModelAdmin):
    list_display = ("drug", "user", "stars", "updated_at")


@admin.register(DrugDiscussionThread)
class DrugDiscussionThreadAdmin(admin.ModelAdmin):
    list_display = ("drug_id",)


@admin.register(DiscussionPost)
class DiscussionPostAdmin(admin.ModelAdmin):
    list_display = ("thread", "user", "created_at")


@admin.register(RelaxAsset)
class RelaxAssetAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "sort_order")
    list_filter = ("category", "is_active")
    search_fields = ("title",)
    fields = ("category", "title", "file", "external_url", "is_active", "sort_order")


@admin.register(FaqItem)
class FaqItemAdmin(admin.ModelAdmin):
    list_display = ("question", "disease", "is_active")


@admin.register(DrugAnalog)
class DrugAnalogAdmin(admin.ModelAdmin):
    list_display = ("drug", "name", "price")


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("slug", "question_text", "answer_type", "is_active", "sort_order")
    list_filter = ("is_active", "answer_type")
    search_fields = ("slug", "title", "question_text")
    ordering = ("sort_order", "id")


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ("user", "survey", "created_at")
    list_filter = ("survey",)
    search_fields = ("user__username", "user__email", "survey__slug")


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "path")


@admin.register(ApiErrorLog)
class ApiErrorLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status_code", "path", "message")


@admin.register(SearchQueryLog)
class SearchQueryLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "query_text", "user")
