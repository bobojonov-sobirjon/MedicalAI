from django.urls import path

from .views import (
    AnalysisOcrFormView,
    MyDiseaseRecordListCreateView,
    MyDiseaseRecordDetailView,
    MyDoctorVisitListCreateView,
    MyDoctorVisitDetailView,
    MyAnalysisListCreateView,
    MyAnalysisDetailView,
    MyPrescriptionListCreateView,
    MyPrescriptionDetailView,
)


urlpatterns = [
    path("me/disease-records/", MyDiseaseRecordListCreateView.as_view(), name="my-disease-records"),
    # Static subpaths must be before /<int:pk>/ so they are not captured as integer pk.
    path("me/disease-records/analyses/ocr/", AnalysisOcrFormView.as_view(), name="my-analysis-ocr-form"),
    path("me/disease-records/analyses/", MyAnalysisListCreateView.as_view(), name="my-analyses"),
    path("me/disease-records/prescriptions/", MyPrescriptionListCreateView.as_view(), name="my-prescriptions"),
    path("me/disease-records/doctor-visits/", MyDoctorVisitListCreateView.as_view(), name="my-doctor-visits"),
    path("me/disease-records/<int:pk>/", MyDiseaseRecordDetailView.as_view(), name="my-disease-record-detail"),
    path("me/doctor-visits/<int:pk>/", MyDoctorVisitDetailView.as_view(), name="my-doctor-visit-detail"),
    path("me/analyses/<int:pk>/", MyAnalysisDetailView.as_view(), name="my-analysis-detail"),
    path("me/prescriptions/<int:pk>/", MyPrescriptionDetailView.as_view(), name="my-prescription-detail"),
]
