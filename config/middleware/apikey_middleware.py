from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse


class BackendApiKeyMiddleware:
    """TZ §3.3 — optional X-Backend-Key for all /api/ routes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.startswith("/api/")
            and getattr(settings, "REQUIRE_BACKEND_API_KEY", False)
            and getattr(settings, "BACKEND_API_KEY", "")
        ):
            key = request.headers.get("X-Backend-Key") or request.META.get("HTTP_X_BACKEND_KEY", "")
            if key != settings.BACKEND_API_KEY:
                return JsonResponse({"detail": "Неверный или отсутствует ключ API (X-Backend-Key)."}, status=401)
        return self.get_response(request)
