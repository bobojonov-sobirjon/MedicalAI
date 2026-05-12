from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from django.conf import settings


class RuTronixConfigError(RuntimeError):
    """Raised when RUTRONIX_API_KEY is missing."""

class RuTronixPaymentRequired(RuntimeError):
    """Raised when organization balance is insufficient (HTTP 402)."""

class RuTronixUnauthorized(RuntimeError):
    """Raised when API key is missing/invalid (HTTP 401)."""


def rutronix_configured() -> bool:
    return bool(getattr(settings, "RUTRONIX_API_KEY", None) and str(settings.RUTRONIX_API_KEY).strip())


def _base_url() -> str:
    return (getattr(settings, "RUTRONIX_BASE_URL", None) or "https://api.rutronix.ai").strip().rstrip("/")


def _model_name() -> str:
    return (getattr(settings, "RUTRONIX_MODEL", None) or "one-perfect-answer").strip()


def chat_completions(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.2,
    max_completion_tokens: int = 2048,
    timeout_s: float = 45.0,
) -> dict[str, Any]:
    """
    RuTronix OpenAI-compatible chat completions.

    Docs: POST /functions/v1/chat-completions, Bearer token auth.
    """
    if not rutronix_configured():
        raise RuTronixConfigError("RUTRONIX_API_KEY is not set")

    url = f"{_base_url()}/functions/v1/chat-completions"
    headers = {
        "Authorization": f"Bearer {settings.RUTRONIX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or _model_name(),
        "messages": messages,
        "temperature": float(temperature),
        "max_completion_tokens": int(max_completion_tokens),
    }

    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code == 401:
            raise RuTronixUnauthorized("RuTronix API key is invalid (401)")
        if r.status_code == 402:
            raise RuTronixPaymentRequired("RuTronix balance is insufficient (402)")
        r.raise_for_status()
        return r.json()


def generate_json(system_instruction: str, user_text: str, *, temperature: float = 0.2) -> dict[str, Any]:
    """
    Text-only completion via RuTronix; expects JSON object in the assistant output.
    """
    # We don't rely on provider-specific "response_mime_type" here; enforce via prompt.
    sys = (
        (system_instruction or "").strip()
        + "\n\n"
        + "Формат ответа: верни ТОЛЬКО JSON-объект без Markdown и без пояснений."
    ).strip()

    resp = chat_completions(
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": (user_text or "").strip()},
        ],
        temperature=temperature,
        max_completion_tokens=2500,
    )

    raw = (
        (resp.get("choices") or [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("Empty RuTronix response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _extract_json_object(raw)

    if not isinstance(data, dict):
        raise RuntimeError("RuTronix returned non-object JSON")
    return data


def _extract_json_object(raw: str) -> dict[str, Any]:
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if not m:
        raise json.JSONDecodeError("No JSON object", raw, 0)
    return json.loads(m.group(0))


def complete_with_image_plain(
    *,
    system_instruction: str,
    user_text: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    temperature: float = 0.1,
    max_completion_tokens: int = 4096,
    timeout_s: float = 120.0,
) -> str:
    """
    OpenAI-style chat completion with one image (data URL) + text; returns assistant plain text.
    Used for lab OCR and drug photo recognition when RuTronix is configured.
    """
    if not rutronix_configured():
        raise RuTronixConfigError("RUTRONIX_API_KEY is not set")

    mt = (mime_type or "image/jpeg").strip()
    if "/" not in mt:
        mt = "image/jpeg"
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mt};base64,{b64}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": (system_instruction or "").strip()},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": (user_text or "").strip()},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    resp = chat_completions(
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_completion_tokens,
        timeout_s=timeout_s,
    )
    raw = (
        (resp.get("choices") or [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    return (raw or "").strip()

