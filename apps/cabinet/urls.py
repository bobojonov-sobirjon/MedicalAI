from django.urls import path

from .views import (
    CabinetItemDetailView,
    CabinetItemListCreateView,
    CabinetRecognizeView,
    DrugRecordViewView,
    RecentDrugViewsView,
)

urlpatterns = [
    path("me/cabinet/items/", CabinetItemListCreateView.as_view(), name="cabinet-items"),
    path("me/cabinet/items/<int:pk>/", CabinetItemDetailView.as_view(), name="cabinet-item-detail"),
    path("me/cabinet/recognize/", CabinetRecognizeView.as_view(), name="cabinet-recognize"),
    path("me/recent-drugs/", RecentDrugViewsView.as_view(), name="recent-drugs"),
    path("catalog/drugs/<int:pk>/view/", DrugRecordViewView.as_view(), name="drug-record-view"),
]
