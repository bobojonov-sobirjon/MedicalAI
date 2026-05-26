from __future__ import annotations

from django.conf import settings


def build_absolute_media_url(request, url: str | None) -> str | None:
    """Build a public absolute URL for a stored media file path or full URL."""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if base:
        if not url.startswith("/"):
            url = "/" + url
        return f"{base}{url}"
    if request is not None:
        try:
            return request.build_absolute_uri(url)
        except Exception:
            return url
    return url


def file_field_url(request, file_field) -> str | None:
    if not file_field:
        return None
    try:
        relative = file_field.url
    except Exception:
        return None
    return build_absolute_media_url(request, relative)
