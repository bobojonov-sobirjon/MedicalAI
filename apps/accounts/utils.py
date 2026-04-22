from __future__ import annotations

from .models import CustomUser


def get_user_by_identifier(identifier: str) -> CustomUser | None:
    """Resolve user by username, email (case-insensitive), or phone_number."""
    raw = (identifier or "").strip()
    if not raw:
        return None
    u = CustomUser.objects.filter(username=raw).first()
    if u:
        return u
    u = CustomUser.objects.filter(email__iexact=raw).first()
    if u:
        return u
    return CustomUser.objects.filter(phone_number=raw).first()
