from django.urls import path

from .views import (
    BodyPartListView,
    PublicDiseaseListView,
    PublicDiseaseDetailView,
    PublicDrugListView,
    PublicDrugDetailView,
    SymptomSearchView,
)


urlpatterns = [
    # Public (mobile app)
    path("catalog/diseases/", PublicDiseaseListView.as_view(), name="public-disease-list"),
    path("catalog/diseases/<int:pk>/", PublicDiseaseDetailView.as_view(), name="public-disease-detail"),
    path("catalog/symptoms/", SymptomSearchView.as_view(), name="symptom-search"),
    path("catalog/body-parts/", BodyPartListView.as_view(), name="body-part-list"),
    path("catalog/drugs/", PublicDrugListView.as_view(), name="public-drug-list"),
    path("catalog/drugs/<int:pk>/", PublicDrugDetailView.as_view(), name="public-drug-detail"),
]

