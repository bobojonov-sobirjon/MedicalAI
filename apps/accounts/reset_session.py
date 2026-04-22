from __future__ import annotations

from django.conf import settings
from django.core import signing

_RESET_SALT = "medicalai-pwd-reset-session"


def create_reset_session_token(user_id: int) -> str:
    signer = signing.TimestampSigner(salt=_RESET_SALT)
    return signer.sign(str(user_id))


def parse_reset_session_token(token: str) -> int:
    signer = signing.TimestampSigner(salt=_RESET_SALT)
    minutes = int(getattr(settings, "PASSWORD_RESET_SESSION_TTL_MINUTES", 15))
    uid = signer.unsign(token, max_age=60 * minutes)
    return int(uid)
