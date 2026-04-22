from django.urls import path

from .views import (
    PublicDiseaseListView,
    PublicDiseaseDetailView,
    PublicDrugListView,
    PublicDrugDetailView,
)


urlpatterns = [
    # Public (mobile app)
    path("catalog/diseases/", PublicDiseaseListView.as_view(), name="public-disease-list"),
    path("catalog/diseases/<int:pk>/", PublicDiseaseDetailView.as_view(), name="public-disease-detail"),
    path("catalog/drugs/", PublicDrugListView.as_view(), name="public-drug-list"),
    path("catalog/drugs/<int:pk>/", PublicDrugDetailView.as_view(), name="public-drug-detail"),
]

