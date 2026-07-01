"""Fixed demo account for App Store / Google Play review."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.billing.models import TariffPlan, UserSubscription
from apps.billing.services import _activate_subscription, get_or_create_billing_profile

from .models import CustomUser, PasswordResetCode


def demo_account_enabled() -> bool:
    return bool(getattr(settings, "DEMO_ACCOUNT_ENABLED", False))


def demo_email() -> str:
    return (getattr(settings, "DEMO_ACCOUNT_EMAIL", "demo@medic-ai.ru") or "").strip().lower()


def demo_username() -> str:
    return (getattr(settings, "DEMO_ACCOUNT_USERNAME", "demo") or "").strip()


def demo_password() -> str:
    return getattr(settings, "DEMO_ACCOUNT_PASSWORD", "Demo1234")


def demo_phone() -> str:
    return (getattr(settings, "DEMO_ACCOUNT_PHONE", "+79001234567") or "").strip()


def demo_otp() -> str:
    return (getattr(settings, "DEMO_ACCOUNT_OTP", "123456") or "123456").strip()


def demo_credentials_public() -> dict:
    return {
        "enabled": demo_account_enabled(),
        "identifier": demo_email(),
        "username": demo_username(),
        "email": demo_email(),
        "phone_number": demo_phone(),
        "password": demo_password(),
        "otp_code": demo_otp(),
        "login_hint": "POST /api/auth/login/ — identifier: email, username или phone_number",
        "forgot_password_hint": (
            "POST /api/auth/password/forgot/request/ then verify (otp_code) then reset "
            "(demo account password is fixed)"
        ),
    }


def matches_demo_identifier(identifier: str) -> bool:
    if not demo_account_enabled():
        return False
    value = (identifier or "").strip()
    if not value:
        return False
    if value.lower() == demo_email():
        return True
    if value == demo_username():
        return True
    if value == demo_phone():
        return True
    return False


def is_demo_user(user: CustomUser | None) -> bool:
    if not demo_account_enabled() or user is None:
        return False
    email = (user.email or "").strip().lower()
    if email and email == demo_email():
        return True
    if user.username == demo_username():
        return True
    return False


def is_demo_otp(code: str) -> bool:
    return demo_account_enabled() and (code or "").strip() == demo_otp()


def ensure_demo_password_reset_code(user: CustomUser) -> None:
    """Persistent OTP row for forgot-password flow (always the same code)."""
    if not is_demo_user(user):
        return
    code = demo_otp()
    PasswordResetCode.objects.filter(user=user).delete()
    PasswordResetCode.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(days=3650),
        used=False,
    )


@transaction.atomic
def ensure_demo_account() -> CustomUser:
    """
    Create or repair the store-review demo user:
    fixed password, premium subscription, persistent OTP.
    """
    email = demo_email()
    username = demo_username()
    password = demo_password()
    phone = demo_phone()

    user = CustomUser.objects.filter(email__iexact=email).first()
    if user is None:
        user = CustomUser.objects.filter(username=username).first()

    if user is None:
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            phone_number=phone,
            first_name="Demo",
            last_name="Reviewer",
            nickname="demo",
            city="Москва",
            is_active=True,
        )
    else:
        user.username = username
        user.email = email
        user.phone_number = phone
        user.is_active = True
        user.save(update_fields=["username", "email", "phone_number", "is_active"])

    user.set_password(password)
    user.save(update_fields=["password"])

    profile = get_or_create_billing_profile(user)
    if not profile.free_trial_used:
        profile.free_trial_used = True
        profile.save(update_fields=["free_trial_used", "updated_at"])

    premium = TariffPlan.objects.filter(slug="premium", is_active=True).first()
    if premium is None:
        premium = TariffPlan.objects.filter(slug="standard", is_active=True).first()
    if premium:
        sub = _activate_subscription(user, premium, source=UserSubscription.Source.ADMIN)
        sub.expires_at = timezone.now() + timedelta(days=3650)
        sub.save(update_fields=["expires_at"])

    ensure_demo_password_reset_code(user)
    return user


def restore_demo_password_if_needed(user: CustomUser) -> None:
    """Keep demo password unchanged after change/reset attempts."""
    if not is_demo_user(user):
        return
    if not user.check_password(demo_password()):
        user.set_password(demo_password())
        user.save(update_fields=["password"])
    ensure_demo_password_reset_code(user)
