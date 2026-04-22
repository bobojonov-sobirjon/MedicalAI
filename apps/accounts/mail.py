from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, code: str) -> None:
    """Send 6-digit verification code to the user's email (TZ §7.5, email channel)."""
    minutes = int(getattr(settings, "PASSWORD_RESET_CODE_TTL_MINUTES", 15))
    subject = "MedicAI — Password reset code"
    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip() or "no-reply@medicalai.local"

    context = {
        "code": code,
        "minutes": minutes,
        "app_name": "MedicAI",
        "support_email": getattr(settings, "DEFAULT_FROM_EMAIL", "") or "support@medicalai.local",
    }

    text_body = (
        f"Your confirmation code: {code}\n\n"
        f"The code is valid for {minutes} minutes.\n"
        "If you did not request a password reset, ignore this email."
    )
    html_body = render_to_string("emails/password_reset.html", context)

    msg = EmailMultiAlternatives(subject=subject, body=text_body, from_email=from_email, to=[to_email])
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)
    logger.info("password reset email sent to=%s", to_email)
