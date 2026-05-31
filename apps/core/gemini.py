from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from django.conf import settings
from PIL import Image

class GeminiConfigError(RuntimeError):
    """Raised when GEMINI_API_KEY is missing or SDK is unavailable."""


class GeminiUnavailableError(RuntimeError):
    """Raised when Gemini rejects the request (e.g. geo restriction on the server)."""


def gemini_configured() -> bool:
    return bool(getattr(settings, "GEMINI_API_KEY", None) and str(settings.GEMINI_API_KEY).strip())


def gemini_fallback_enabled() -> bool:
    return bool(getattr(settings, "USE_GEMINI_FALLBACK", False))


def _model_name() -> str:
    return (getattr(settings, "GEMINI_MODEL", None) or "gemini-2.0-flash").strip()


def normalize_lab_ocr_plain_text(raw: str) -> str:
    """
    Post-process OCR: remove ``` / ```json fences; if fenced body is JSON, pretty-print as plain text
    (field `result_text` stays a string, not a nested JSON object in the API).
    """
    t = (raw or "").strip()
    if not t:
        return t

    def _try_json_pretty(inner: str) -> str | None:
        inner = inner.strip()
        if not inner:
            return inner
        try:
            obj = json.loads(inner)
        except json.JSONDecodeError:
            return None
        if isinstance(obj, (dict, list)):
            return json.dumps(obj, ensure_ascii=False, indent=2)
        return str(obj)

    m = re.match(r"^```(?:[a-zA-Z0-9_-]+)?\s*\r?\n([\s\S]*?)\r?\n```\s*$", t)
    if m:
        inner = m.group(1)
        pretty = _try_json_pretty(inner)
        return pretty if pretty is not None else inner.strip()

    def repl(mm: re.Match) -> str:
        inner = mm.group(1)
        pretty = _try_json_pretty(inner)
        return pretty if pretty is not None else inner.strip()

    return re.sub(r"```(?:json)?\s*\r?\n([\s\S]*?)\r?\n```", repl, t).strip()


def _strip_all_md_emphasis(s: str) -> str:
    """Remove Markdown **bold** and *italic* (common OCR noise for mobile)."""
    t = s or ""
    for _ in range(12):
        n = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
        if n == t:
            break
        t = n
    for _ in range(8):
        n = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", t)
        if n == t:
            break
        t = n
    return t


def _strip_md_bold(s: str) -> str:
    return _strip_all_md_emphasis(s or "")


def _pipe_row_cells(line: str) -> list[str]:
    return [_strip_md_bold(c).strip() for c in line.strip().strip("|").split("|")]


def _is_md_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.match(r"^[\s\-:|\u2013]+$", c) for c in cells)


def _pipe_table_to_plain(tbl_lines: list[str]) -> str:
    """GitHub-style | table | -> bullet blocks for mobile clients (no Markdown)."""
    rows: list[list[str]] = []
    for ln in tbl_lines:
        if "|" not in ln:
            continue
        cells = _pipe_row_cells(ln)
        if not cells:
            continue
        if _is_md_separator_row(cells):
            continue
        rows.append(cells)
    if len(rows) < 2:
        return "\n".join(_strip_md_bold(x) for x in tbl_lines).strip()

    header = rows[0]
    blocks: list[str] = []
    for cells in rows[1:]:
        if len(cells) != len(header):
            blocks.append(" — ".join(cells))
            continue
        title = cells[0] or "—"
        pairs = [f"{header[j]}: {cells[j]}" for j in range(1, len(header)) if cells[j]]
        if pairs:
            blocks.append(f"• {title}\n  " + "\n  ".join(pairs))
        else:
            blocks.append(f"• {title}")
    return "\n\n".join(blocks).strip()


def format_lab_ocr_for_client(text: str) -> str:
    """
    Normalize OCR output for API/mobile: Markdown pipe tables -> structured plain text,
    strip **bold** markers, collapse excessive blank lines.
    """
    raw = (text or "").strip()
    if not raw:
        return raw

    lines = raw.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if "|" in ln and ln.count("|") >= 2:
            start = i
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                i += 1
            out.append(_pipe_table_to_plain(lines[start:i]))
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        out.append(_strip_md_bold(ln).rstrip())
        i += 1

    merged = "\n".join(out).strip()
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    return _strip_all_md_emphasis(merged).strip()


def is_lab_ocr_rejection_message(text: str) -> bool:
    """Model says the image is not a lab document — replace entire result_text with this message."""
    return "не видно бланка анализа" in (text or "").casefold()


def sanitize_prior_analysis_result_text(s: str) -> str:
    """Strip ```…``` blocks, drop junk segments, then rebuild with a single OCR separator style."""
    t = s or ""
    while True:
        n = re.sub(r"```[a-zA-Z0-9_-]*\s*\r?\n[\s\S]*?\r?\n```", "", t)
        if n == t:
            break
        t = n
    t = re.sub(r"(?:\n\n--- OCR ---\n\n)+", "\n\n--- OCR ---\n\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    def _probable_ui_json_blob(p: str) -> bool:
        st = p.strip()
        if not st.startswith("{"):
            return False
        try:
            d = json.loads(st)
        except json.JSONDecodeError:
            return False
        if not isinstance(d, dict):
            return False
        keys = set(d.keys())
        if "navigation" in keys:
            return True
        if "header" in keys and "main_content" in keys:
            return True
        return False

    parts = [p.strip() for p in t.split("\n\n--- OCR ---\n\n")]
    kept: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.casefold() == "string":
            continue
        if is_lab_ocr_rejection_message(p):
            continue
        if _probable_ui_json_blob(p):
            continue
        kept.append(p)
    return "\n\n--- OCR ---\n\n".join(kept).strip()


def merge_lab_ocr_result_text(*, old: str | None, new: str, mode: str) -> str:
    """
    Build final `result_text` after an OCR run.
    - If the new run is the “not a lab document” message → whole field becomes only that (drops junk).
    - replace → new only.
    - append → old text cleaned (no fenced blocks) + separator + new.
    """
    new = (new or "").strip()
    if is_lab_ocr_rejection_message(new):
        return new
    if (mode or "").lower() == "replace":
        return new
    base = sanitize_prior_analysis_result_text(old or "")
    if not base:
        return new
    return f"{base}\n\n--- OCR ---\n\n{new}"


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

    if gemini_fallback_enabled() and gemini_configured():
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

    raise GeminiConfigError("Настройте RUTRONIX_API_KEY (и RUTRONIX_MODEL для текста).")


def transcribe_lab_image(image_bytes: bytes, _mime_type: str = "image/jpeg") -> str:
    """OCR-style plain text for medical lab reports (Russian)."""
    system = (
        "Ты извлекаешь текст только с бланков/результатов медицинских анализов (лаборатория, УЗИ-заключение, выписка с показателями). "
        "Если на фото нет медицинского документа (скриншот приложения, меню кафе, реклама и т.п.) — ответь одной короткой строкой на русском: "
        "«На изображении не видно бланка анализа. Загрузите фото бланка или результатов анализа.» "
        "Не придумывай JSON, таблицы интерфейсов и навигацию сайтов. "
        "Формат ответа: обычный текст, без Markdown, без блоков ``` и без обёртки JSON."
    )
    prompt = (
        "Извлеки читаемый текст с медицинского документа: названия показателей, значения, единицы, референсы, даты. "
        "Если это не медицинский документ — одна короткая фраза из системной инструкции."
    )
    try:
        from .rutronix import RuTronixConfigError, complete_with_image_plain, rutronix_configured
    except Exception:  # pragma: no cover
        complete_with_image_plain = None
        rutronix_configured = lambda: False  # type: ignore
        RuTronixConfigError = RuntimeError  # type: ignore

    if complete_with_image_plain and rutronix_configured():
        text = complete_with_image_plain(
            system_instruction=system,
            user_text=prompt,
            image_bytes=image_bytes,
            mime_type=_mime_type,
            temperature=0.1,
        )
        return normalize_lab_ocr_plain_text(text)

    if gemini_fallback_enabled() and gemini_configured():
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(_model_name(), system_instruction=system)
        pil = Image.open(BytesIO(image_bytes))
        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGB")
        resp = model.generate_content([prompt, pil], generation_config=genai.GenerationConfig(temperature=0.1))
        return normalize_lab_ocr_plain_text((resp.text or "").strip())

    raise GeminiConfigError("Настройте RUTRONIX_API_KEY и RUTRONIX_VISION_MODEL для OCR.")


_DRUG_VISION_SYSTEM = (
    "Ты распознаёшь торговые названия лекарств на фото упаковок (рынок РФ/СНГ). "
    "Бери крупное торговое название на упаковке (например «Эликвис», а не «апиксабан»). "
    "Не включай дозировку, форму выпуска и производителя."
)


def _complete_drug_vision_plain(
    *,
    system_instruction: str,
    user_text: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    try:
        from .rutronix import (
            RuTronixPaymentRequired,
            RuTronixUpstreamError,
            complete_with_image_plain,
            rutronix_configured,
        )
    except Exception:  # pragma: no cover
        complete_with_image_plain = None
        rutronix_configured = lambda: False  # type: ignore
        RuTronixUpstreamError = RuntimeError  # type: ignore
        RuTronixPaymentRequired = RuntimeError  # type: ignore

    rutronix_failed: BaseException | None = None
    if complete_with_image_plain and rutronix_configured():
        try:
            return complete_with_image_plain(
                system_instruction=system_instruction,
                user_text=user_text,
                image_bytes=image_bytes,
                mime_type=mime_type,
                temperature=0.1,
            )
        except (RuTronixUpstreamError, RuTronixPaymentRequired) as exc:
            rutronix_failed = exc

    if gemini_fallback_enabled() and gemini_configured():
        try:
            return _gemini_vision_plain(
                system_instruction=system_instruction,
                user_text=user_text,
                image_bytes=image_bytes,
            )
        except GeminiUnavailableError as exc:
            if rutronix_failed is not None:
                raise rutronix_failed from exc
            raise

    if rutronix_failed is not None:
        raise rutronix_failed

    raise GeminiConfigError("Настройте RUTRONIX_API_KEY и RUTRONIX_VISION_MODEL для распознавания по фото.")


def _gemini_vision_plain(
    *,
    system_instruction: str,
    user_text: str,
    image_bytes: bytes,
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(_model_name(), system_instruction=system_instruction)
    pil = Image.open(BytesIO(image_bytes))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    try:
        resp = model.generate_content(
            [user_text, pil],
            generation_config=genai.GenerationConfig(temperature=0.1),
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "location is not supported" in msg or "user location" in msg:
            raise GeminiUnavailableError(
                "Gemini API недоступен в регионе сервера (geo restriction). "
                "На production используйте RUTRONIX_API_KEY — Gemini с VPS часто блокируется."
            ) from exc
        raise
    return (resp.text or "").strip()


def _normalize_drug_name_line(raw: str) -> str:
    line = (raw or "").strip().split("\n")[0].strip()
    line = re.sub(r'^[\d\.\-\*\)]+\s*', "", line).strip(" \"'«»")
    return line[:255]


def _parse_drug_names_json(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    payload: Any
    try:
        payload = _extract_json_object(text)
    except json.JSONDecodeError:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            names = [_normalize_drug_name_line(part) for part in re.split(r"[\n,;]+", text)]
            return [n for n in names if n and not n.lower().startswith("не удалось")]

    if isinstance(payload, dict):
        items = payload.get("drugs") or payload.get("items") or payload.get("names") or []
    elif isinstance(payload, list):
        items = payload
    else:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = _normalize_drug_name_line(str(item))
        if not name or name.lower().startswith("не удалось"):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def recognize_drug_name_from_image(image_bytes: bytes, _mime_type: str = "image/jpeg") -> str:
    """Return best-effort commercial drug name from packaging photo (Russian market)."""
    text = _complete_drug_vision_plain(
        system_instruction=_DRUG_VISION_SYSTEM,
        user_text=(
            "На фото одна упаковка лекарства. "
            "Ответь одной строкой: только торговое название. "
            "Если не уверен — «Не удалось распознать»."
        ),
        image_bytes=image_bytes,
        mime_type=_mime_type,
    )
    return _normalize_drug_name_line(text)


def recognize_drug_names_from_image(image_bytes: bytes, _mime_type: str = "image/jpeg") -> list[str]:
    """Return all visible commercial drug names from a photo (one or many packages)."""
    text = _complete_drug_vision_plain(
        system_instruction=_DRUG_VISION_SYSTEM,
        user_text=(
            "На фото может быть одна или несколько упаковок лекарств. "
            "Верни JSON без markdown: {\"drugs\": [\"Название1\", \"Название2\"]}. "
            "Только торговые названия. Если ничего не видно — {\"drugs\": []}."
        ),
        image_bytes=image_bytes,
        mime_type=_mime_type,
    )
    names = _parse_drug_names_json(text)
    if names:
        return names
    single = _normalize_drug_name_line(text)
    if single and not single.lower().startswith("не удалось") and not single.startswith("{"):
        return [single]
    return []


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Fallback if model wraps JSON in markdown fences."""
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if not m:
        raise json.JSONDecodeError("No JSON object", raw, 0)
    return json.loads(m.group(0))
