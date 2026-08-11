from __future__ import annotations

from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.billing.services import get_access_scope, get_paywall_payload


class SubscriptionAccessMiddleware:
    """
    Restrict authenticated users without full access to history (+ picker helpers).
    Trial / paid users get full API access.
    """

    ALWAYS_ALLOWED_PREFIXES = (
        "/api/auth/",
        "/api/billing/",
        "/api/me/profiles/",
        "/api/content/config/",
        "/api/content/pages/",
        "/api/faq/",
        # Справочник болезней нужен и для истории, и для каталога — не режем paywall'ом.
        "/api/catalog/diseases/",
    )
    HISTORY_ONLY_PREFIXES = (
        "/api/me/disease-records/",
        "/api/me/doctor-visits/",
        "/api/me/analyses/",
        "/api/me/prescriptions/",
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_authentication = JWTAuthentication()

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        if self._is_always_allowed(request.path):
            return self.get_response(request)

        user = self._authenticate_request_user(request)
        if user is None or not user.is_authenticated or getattr(user, "is_staff", False):
            return self.get_response(request)

        if get_access_scope(user) == "full" or self._is_history_allowed(request.path):
            return self.get_response(request)

        payload = get_paywall_payload()
        return JsonResponse(
            {
                "detail": payload["message"],
                "code": "subscription_required",
                "access_scope": "history_only",
                "allowed_sections": ["history"],
                "paywall": payload,
            },
            status=403,
        )

    def _authenticate_request_user(self, request):
        try:
            auth_result = self.jwt_authentication.authenticate(request)
        except (InvalidToken, TokenError):
            return None
        if not auth_result:
            return None
        user, _token = auth_result
        return user

    def _is_always_allowed(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self.ALWAYS_ALLOWED_PREFIXES)

    def _is_history_allowed(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in self.HISTORY_ONLY_PREFIXES)
