from __future__ import annotations

import base64
import json
import re
from io import BytesIO
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


def _http_timeout_chat_s() -> float:
    return float(getattr(settings, "RUTRONIX_CHAT_TIMEOUT_S", 45.0))


def _vision_httpx_timeout() -> httpx.Timeout:
    """Vision: keep each phase bounded; whole OCR wall time must stay under Gunicorn --timeout."""
    read_s = float(getattr(settings, "RUTRONIX_VISION_READ_S", 90.0))
    write_s = float(getattr(settings, "RUTRONIX_VISION_WRITE_S", 120.0))
    connect_s = float(getattr(settings, "RUTRONIX_VISION_CONNECT_S", 12.0))
    # pool: acquiring connection from pool (rare stall)
    return httpx.Timeout(connect=connect_s, read=read_s, write=write_s, pool=5.0)


def _downsample_image_for_vision_api(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """
    Shrink + JPEG-recompress lab/drug photos so RuTronix JSON body uploads fast (avoids Gunicorn worker kill).
    """
    from PIL import Image

    max_side = int(getattr(settings, "RUTRONIX_VISION_MAX_IMAGE_SIDE", 1280))
    quality = int(getattr(settings, "RUTRONIX_VISION_JPEG_QUALITY", 82))
    quality = max(40, min(quality, 95))

    try:
        im = Image.open(BytesIO(image_bytes))
    except Exception:
        return image_bytes, mime_type

    if im.mode in ("RGBA", "P"):
        if im.mode == "RGBA":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        else:
            im = im.convert("RGB")
    elif im.mode != "RGB":
        im = im.convert("RGB")

    w, h = im.size
    if w < 1 or h < 1:
        return image_bytes, mime_type
    if max(w, h) > max_side:
        ratio = max_side / float(max(w, h))
        im = im.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.Resampling.LANCZOS)

    out = BytesIO()
    im.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def _assistant_text_from_message(msg: dict[str, Any] | None) -> str:
    """Normalize OpenAI-style assistant message `content` (str or list of parts) to plain text."""
    if not isinstance(msg, dict):
        return ""
    content: Any = msg.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                ptype = part.get("type")
                if ptype == "text":
                    parts.append(str(part.get("text") or ""))
                elif ptype == "refusal":
                    parts.append(str(part.get("refusal") or ""))
        return "".join(parts).strip()
    if content is None:
        return ""
    return str(content).strip()


def chat_completions(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.2,
    max_completion_tokens: int = 2048,
    timeout: float | httpx.Timeout | None = None,
) -> dict[str, Any]:
    """
    RuTronix OpenAI-compatible chat completions.

    Docs: POST /functions/v1/chat-completions, Bearer token auth.
    """
    if not rutronix_configured():
        raise RuTronixConfigError("RUTRONIX_API_KEY is not set")

    client_timeout: float | httpx.Timeout
    if timeout is None:
        client_timeout = _http_timeout_chat_s()
    else:
        client_timeout = timeout

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

    with httpx.Client(timeout=client_timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code == 401:
            raise RuTronixUnauthorized("RuTronix API key is invalid (401)")
        if r.status_code == 402:
            raise RuTronixPaymentRequired("RuTronix balance is insufficient (402)")
        r.raise_for_status()
        try:
            data = r.json()
        except json.JSONDecodeError as e:
            raise RuntimeError(f"RuTronix response is not JSON: {e}") from e
        if not isinstance(data, dict):
            raise RuntimeError(f"RuTronix returned unexpected JSON root type: {type(data).__name__}")
        return data


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

    raw = _assistant_text_from_message((resp.get("choices") or [{}])[0].get("message") or {})
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
    image_bytes, mt = _downsample_image_for_vision_api(image_bytes, mt)
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
        timeout=_vision_httpx_timeout(),
    )
    return _assistant_text_from_message((resp.get("choices") or [{}])[0].get("message") or {})

