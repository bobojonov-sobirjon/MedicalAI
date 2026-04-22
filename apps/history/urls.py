from django.urls import path

from .views import (
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
    path("me/disease-records/<int:pk>/", MyDiseaseRecordDetailView.as_view(), name="my-disease-record-detail"),

    # doctor visits (many per record)
    path("me/disease-records/<int:record_id>/doctor-visits/", MyDoctorVisitListCreateView.as_view(), name="my-doctor-visits"),
    path("me/doctor-visits/<int:pk>/", MyDoctorVisitDetailView.as_view(), name="my-doctor-visit-detail"),

    # analyses (many per record)
    path("me/disease-records/<int:record_id>/analyses/", MyAnalysisListCreateView.as_view(), name="my-analyses"),
    path("me/analyses/<int:pk>/", MyAnalysisDetailView.as_view(), name="my-analysis-detail"),

    # prescriptions (many per record)
    path("me/disease-records/<int:record_id>/prescriptions/", MyPrescriptionListCreateView.as_view(), name="my-prescriptions"),
    path("me/prescriptions/<int:pk>/", MyPrescriptionDetailView.as_view(), name="my-prescription-detail"),
]

