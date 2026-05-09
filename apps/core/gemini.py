from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from django.conf import settings
from PIL import Image

class GeminiConfigError(RuntimeError):
    """Raised when GEMINI_API_KEY is missing or SDK is unavailable."""


def gemini_configured() -> bool:
    return bool(getattr(settings, "GEMINI_API_KEY", None) and str(settings.GEMINI_API_KEY).strip())


def _model_name() -> str:
    return (getattr(settings, "GEMINI_MODEL", None) or "gemini-2.0-flash").strip()


def generate_json(system_instruction: str, user_text: str, *, temperature: float = 0.2) -> dict[str, Any]:
    """
    Text-only completion; response parsed as JSON object.
    """
    # Prefer RuTronix for text tasks when configured (customer request).
    try:
        from .rutronix import generate_json as rutronix_generate_json
        from .rutronix import rutronix_configured
    except Exception:  # pragma: no cover
        rutronix_generate_json = None
        rutronix_configured = lambda: False  # type: ignore

    if rutronix_configured() and rutronix_generate_json:
        return rutronix_generate_json(system_instruction, user_text, temperature=temperature)

    if not gemini_configured():
        raise GeminiConfigError("GEMINI_API_KEY is not set")

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(_model_name(), system_instruction=system_instruction)
    resp = model.generate_content(
        user_text,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    raw = (resp.text or "").strip()
    if not raw:
        raise RuntimeError("Empty Gemini response")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = _extract_json_object(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Gemini returned non-object JSON")
    return data


def transcribe_lab_image(image_bytes: bytes, _mime_type: str = "image/jpeg") -> str:
    """OCR-style plain text for medical lab reports (Russian)."""
    system = (
        "Ты помощник для извлечения текста с фото медицинского анализа. "
        "Верни только структурированный текст результатов, без диагнозов и без советов врача. "
        "Если текст нечитаем — верни краткое сообщение об этом."
    )
    prompt = "Извлеки весь читаемый текст с изображения (заголовки, показатели, единицы, референсы)."
    if not gemini_configured():
        raise GeminiConfigError("GEMINI_API_KEY is not set")

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(_model_name(), system_instruction=system)
    pil = Image.open(BytesIO(image_bytes))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    resp = model.generate_content([prompt, pil], generation_config=genai.GenerationConfig(temperature=0.1))
    return (resp.text or "").strip()


def recognize_drug_name_from_image(image_bytes: bytes, _mime_type: str = "image/jpeg") -> str:
    """Return best-effort commercial drug name from packaging photo (Russian market)."""
    system = (
        "Ты распознаёшь торговое название лекарства с фото упаковки. "
        "Ответь одной строкой: только название препарата как на упаковке, без пояснений. "
        "Если не уверен — кратко: Не удалось распознать."
    )
    if not gemini_configured():
        raise GeminiConfigError("GEMINI_API_KEY is not set")

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(_model_name(), system_instruction=system)
    pil = Image.open(BytesIO(image_bytes))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    resp = model.generate_content(
        ["Какое название лекарства на фото? Одна строка.", pil],
        generation_config=genai.GenerationConfig(temperature=0.1),
    )
    return (resp.text or "").strip().split("\n")[0].strip()[:255]


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Fallback if model wraps JSON in markdown fences."""
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if not m:
        raise json.JSONDecodeError("No JSON object", raw, 0)
    return json.loads(m.group(0))
