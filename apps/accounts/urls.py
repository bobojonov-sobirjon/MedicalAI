from django.urls import path

from .views import (
    RegisterView,
    LoginView,
    RefreshTokenView,
    MeView,
    SocialLoginView,
    PasswordChangeView,
    ForgotPasswordRequestView,
    ForgotPasswordVerifyView,
    ForgotPasswordResetView,
    DemoCredentialsView,
)
from .profile_views import ProfileDetailView, ProfileListView


urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/demo/", DemoCredentialsView.as_view(), name="auth-demo"),
    path("auth/refresh/", RefreshTokenView.as_view(), name="auth-refresh"),
    path("auth/password/forgot/request/", ForgotPasswordRequestView.as_view(), name="auth-password-forgot-request"),
    path("auth/password/forgot/verify/", ForgotPasswordVerifyView.as_view(), name="auth-password-forgot-verify"),
    path("auth/password/forgot/reset/", ForgotPasswordResetView.as_view(), name="auth-password-forgot-reset"),
    path("auth/password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/social/", SocialLoginView.as_view(), name="auth-social"),
    path("me/profiles/", ProfileListView.as_view(), name="me-profiles"),
    path("me/profiles/<int:profile_id>/", ProfileDetailView.as_view(), name="me-profile-detail"),
]
