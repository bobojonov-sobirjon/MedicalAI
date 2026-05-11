from django.urls import path

from .views import (
    AnalysisOcrView,
    MyDiseaseRecordListCreateView,
    MyDiseaseRecordDetailView,
    MyDoctorVisitListCreateView,
    MyDoctorVisitBulkCreateView,
    MyDoctorVisitDetailView,
    MyAnalysisListCreateView,
    MyAnalysisBulkCreateView,
    MyAnalysisDetailView,
    MyPrescriptionListCreateView,
    MyPrescriptionBulkCreateView,
    MyPrescriptionDetailView,
)


urlpatterns = [
    path("me/disease-records/", MyDiseaseRecordListCreateView.as_view(), name="my-disease-records"),
    path("me/disease-records/<int:pk>/", MyDiseaseRecordDetailView.as_view(), name="my-disease-record-detail"),

    # doctor visits (many per record)
    path("me/disease-records/<int:record_id>/doctor-visits/", MyDoctorVisitListCreateView.as_view(), name="my-doctor-visits"),
    path("me/disease-records/<int:record_id>/doctor-visits/bulk/", MyDoctorVisitBulkCreateView.as_view(), name="my-doctor-visits-bulk"),
    path("me/doctor-visits/<int:pk>/", MyDoctorVisitDetailView.as_view(), name="my-doctor-visit-detail"),

    # analyses (many per record)
    path("me/disease-records/<int:record_id>/analyses/", MyAnalysisListCreateView.as_view(), name="my-analyses"),
    path("me/disease-records/<int:record_id>/analyses/bulk/", MyAnalysisBulkCreateView.as_view(), name="my-analyses-bulk"),
    path("me/analyses/<int:pk>/", MyAnalysisDetailView.as_view(), name="my-analysis-detail"),
    path("me/analyses/<int:pk>/ocr/", AnalysisOcrView.as_view(), name="my-analysis-ocr"),

    # prescriptions (many per record)
    path("me/disease-records/<int:record_id>/prescriptions/", MyPrescriptionListCreateView.as_view(), name="my-prescriptions"),
    path("me/disease-records/<int:record_id>/prescriptions/bulk/", MyPrescriptionBulkCreateView.as_view(), name="my-prescriptions-bulk"),
    path("me/prescriptions/<int:pk>/", MyPrescriptionDetailView.as_view(), name="my-prescription-detail"),
]

