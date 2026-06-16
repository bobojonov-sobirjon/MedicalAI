from __future__ import annotations

import hashlib
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings


def _md5_upper(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().upper()


def robokassa_configured() -> bool:
    return bool(
        getattr(settings, "ROBOKASSA_MERCHANT_LOGIN", "").strip()
        and getattr(settings, "ROBOKASSA_PASSWORD1", "").strip()
        and getattr(settings, "ROBOKASSA_PASSWORD2", "").strip()
    )


def payment_signature(*, merchant_login: str, out_sum: str, inv_id: int, password1: str) -> str:
    """Подпись для перехода на оплату: MerchantLogin:OutSum:InvId:Password1"""
    raw = f"{merchant_login}:{out_sum}:{inv_id}:{password1}"
    return _md5_upper(raw)


def result_signature(*, out_sum: str, inv_id: int, password2: str) -> str:
    """Подпись Result URL: OutSum:InvId:Password2"""
    raw = f"{out_sum}:{inv_id}:{password2}"
    return _md5_upper(raw)


def success_signature(*, out_sum: str, inv_id: int, password1: str) -> str:
    """Подпись Success URL: OutSum:InvId:Password1"""
    raw = f"{out_sum}:{inv_id}:{password1}"
    return _md5_upper(raw)


def format_out_sum(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01'))}"


def build_payment_url(*, inv_id: int, amount: Decimal, description: str) -> str:
    login = settings.ROBOKASSA_MERCHANT_LOGIN.strip()
    password1 = settings.ROBOKASSA_PASSWORD1.strip()
    out_sum = format_out_sum(amount)
    sig = payment_signature(
        merchant_login=login,
        out_sum=out_sum,
        inv_id=inv_id,
        password1=password1,
    )
    base = getattr(settings, "ROBOKASSA_PAYMENT_URL", "https://auth.robokassa.ru/Merchant/Index.aspx")
    params = {
        "MerchantLogin": login,
        "OutSum": out_sum,
        "InvId": inv_id,
        "Description": description[:255],
        "SignatureValue": sig,
    }
    if getattr(settings, "ROBOKASSA_TEST_MODE", True):
        params["IsTest"] = 1

    # Success/Fail URL — лучше задать в ЛК Robokassa, а не в ссылке (иначе возможна ошибка подписи).
    if getattr(settings, "ROBOKASSA_APPEND_REDIRECT_URLS", False):
        public_base = getattr(settings, "PUBLIC_BASE_URL", "").strip().rstrip("/")
        success = getattr(settings, "ROBOKASSA_SUCCESS_URL", "").strip() or (
            f"{public_base}/api/billing/robokassa/success/" if public_base else ""
        )
        fail = getattr(settings, "ROBOKASSA_FAIL_URL", "").strip() or (
            f"{public_base}/api/billing/robokassa/fail/" if public_base else ""
        )
        if success:
            params["SuccessUrl"] = success
        if fail:
            params["FailUrl"] = fail

    return f"{base}?{urlencode(params)}"


def verify_result_signature(*, out_sum: str, inv_id: int, signature_value: str) -> bool:
    password2 = settings.ROBOKASSA_PASSWORD2.strip()
    expected = result_signature(out_sum=out_sum, inv_id=inv_id, password2=password2)
    return (signature_value or "").strip().upper() == expected


def verify_success_signature(*, out_sum: str, inv_id: int, signature_value: str) -> bool:
    password1 = settings.ROBOKASSA_PASSWORD1.strip()
    expected = success_signature(out_sum=out_sum, inv_id=inv_id, password1=password1)
    return (signature_value or "").strip().upper() == expected
