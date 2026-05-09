from django.urls import path

from . import views

urlpatterns = [
    path("content/pages/<slug:slug>/", views.StaticPageView.as_view(), name="static-page"),
    path("content/config/", views.AppConfigView.as_view(), name="app-config"),
    path("geo/cities/", views.CityListView.as_view(), name="geo-cities"),
    path("geo/facilities/", views.FacilityListView.as_view(), name="geo-facilities"),
    path("geo/facilities/<int:pk>/", views.FacilityDetailView.as_view(), name="geo-facility-detail"),
    path("me/notifications/useful/", views.UsefulCombinedFeedView.as_view(), name="notifications-useful"),
    path("me/notifications/useful/seen/", views.UsefulMarkSeenView.as_view(), name="notifications-useful-seen"),
    path("me/tip-settings/", views.UserTipSettingsView.as_view(), name="tip-settings"),
    path("me/disease-tip-subscribe/<int:disease_id>/", views.DiseaseTipSubscribeView.as_view(), name="disease-tip-sub"),
    path("me/notifications/events/", views.NotificationEventListCreateView.as_view(), name="notification-events"),
    path("me/notifications/events/<int:pk>/read/", views.NotificationMarkReadView.as_view(), name="notification-read"),
    path("me/notifications/badge/", views.NotificationBadgeView.as_view(), name="notification-badge"),
    path("support/feedback/", views.FeedbackCreateView.as_view(), name="support-feedback"),
    path("support/psychology/", views.PsychologyInquiryView.as_view(), name="support-psychology"),
    path("me/chat/threads/", views.ChatThreadListCreateView.as_view(), name="chat-threads"),
    path("me/chat/threads/<int:thread_id>/messages/", views.ChatMessageListCreateView.as_view(), name="chat-messages"),
    path("catalog/drugs/<int:drug_id>/reviews/", views.DrugReviewListCreateView.as_view(), name="drug-reviews"),
    path("catalog/drugs/<int:drug_id>/star-rating/", views.DrugStarRatingView.as_view(), name="drug-star"),
    path("catalog/drugs/<int:drug_id>/discussion/", views.DrugDiscussionView.as_view(), name="drug-discuss"),
    path("catalog/drugs/<int:drug_id>/analogs/", views.DrugAnalogListView.as_view(), name="drug-analogs"),
    path("relax/feed/", views.RelaxFeedView.as_view(), name="relax-feed"),
    path("faq/", views.FaqSearchView.as_view(), name="faq-search"),
    path("me/survey/", views.SurveySubmitView.as_view(), name="survey-submit"),
    path("me/family/", views.FamilyLinkListCreateView.as_view(), name="family-list"),
    path("me/family/<int:member_id>/", views.FamilyLinkDeleteView.as_view(), name="family-delete"),
    path("admin/metrics/summary/", views.AdminSummaryView.as_view(), name="admin-metrics"),
    path("me/voice/transcribe/", views.VoiceTranscribeView.as_view(), name="voice-transcribe"),
]
