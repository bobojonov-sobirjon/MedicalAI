from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from .demo import demo_otp, is_demo_user
from .models import CustomUser, PasswordResetCode


def issue_password_reset_code(user: CustomUser) -> str:
    """Create a new one-time code; invalidates previous unused codes for this user."""
    if is_demo_user(user):
        from .demo import ensure_demo_password_reset_code

        ensure_demo_password_reset_code(user)
        return demo_otp()

    PasswordResetCode.objects.filter(user=user, used=False).delete()
    code = f"{secrets.randbelow(1_000_000):06d}"
    ttl_min = int(getattr(settings, "PASSWORD_RESET_CODE_TTL_MINUTES", 15))
    PasswordResetCode.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=ttl_min),
    )
    return code
