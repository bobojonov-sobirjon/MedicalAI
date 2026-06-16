from django.urls import path

from . import views

urlpatterns = [
    path("billing/tariffs/", views.TariffListView.as_view(), name="billing-tariffs"),
    path("billing/subscription/", views.MySubscriptionView.as_view(), name="billing-subscription"),
    path("billing/payments/", views.MyPaymentsView.as_view(), name="billing-payments"),
    path("billing/payments/create/", views.CreatePaymentView.as_view(), name="billing-payment-create"),
    path("billing/payments/<int:payment_id>/", views.PaymentDetailView.as_view(), name="billing-payment-detail"),
    path("billing/robokassa/result/", views.RobokassaResultView.as_view(), name="billing-robokassa-result"),
    path("billing/robokassa/success/", views.RobokassaSuccessView.as_view(), name="billing-robokassa-success"),
    path("billing/robokassa/fail/", views.RobokassaFailView.as_view(), name="billing-robokassa-fail"),
]
