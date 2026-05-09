from django.urls import path

from .views import DiagnoseView, MyAssistantDiagnosisDetailView, MyAssistantDiagnosisListView

urlpatterns = [
    path("assistant/diagnose/", DiagnoseView.as_view(), name="assistant-diagnose"),
    path("assistant/diagnoses/", MyAssistantDiagnosisListView.as_view(), name="assistant-diagnosis-list"),
    path("assistant/diagnoses/<int:pk>/", MyAssistantDiagnosisDetailView.as_view(), name="assistant-diagnosis-detail"),
]
