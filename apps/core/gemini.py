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


def _strip_md_bold(s: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", s or "")


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
    return merged.strip()


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
        from .rutronix import complete_with_image_plain, rutronix_configured
    except Exception:  # pragma: no cover
        complete_with_image_plain = None
        rutronix_configured = lambda: False  # type: ignore

    if complete_with_image_plain and rutronix_configured():
        text = complete_with_image_plain(
            system_instruction=system,
            user_text=prompt,
            image_bytes=image_bytes,
            mime_type=_mime_type,
            temperature=0.1,
        )
        return normalize_lab_ocr_plain_text(text)

    if not gemini_configured():
        raise GeminiConfigError("Настройте RUTRONIX_API_KEY (OCR) или GEMINI_API_KEY.")

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(_model_name(), system_instruction=system)
    pil = Image.open(BytesIO(image_bytes))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    resp = model.generate_content([prompt, pil], generation_config=genai.GenerationConfig(temperature=0.1))
    return normalize_lab_ocr_plain_text((resp.text or "").strip())


def recognize_drug_name_from_image(image_bytes: bytes, _mime_type: str = "image/jpeg") -> str:
    """Return best-effort commercial drug name from packaging photo (Russian market)."""
    system = (
        "Ты распознаёшь торговое название лекарства с фото упаковки. "
        "Ответь одной строкой: только название препарата как на упаковке, без пояснений. "
        "Если не уверен — кратко: Не удалось распознать."
    )
    user_q = "Какое название лекарства на фото? Одна строка."

    try:
        from .rutronix import complete_with_image_plain, rutronix_configured
    except Exception:  # pragma: no cover
        complete_with_image_plain = None
        rutronix_configured = lambda: False  # type: ignore

    if complete_with_image_plain and rutronix_configured():
        text = complete_with_image_plain(
            system_instruction=system,
            user_text=user_q,
            image_bytes=image_bytes,
            mime_type=_mime_type,
            temperature=0.1,
        )
        return (text or "").strip().split("\n")[0].strip()[:255]

    if not gemini_configured():
        raise GeminiConfigError("Настройте RUTRONIX_API_KEY (распознавание) или GEMINI_API_KEY.")

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(_model_name(), system_instruction=system)
    pil = Image.open(BytesIO(image_bytes))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    resp = model.generate_content(
        [user_q, pil],
        generation_config=genai.GenerationConfig(temperature=0.1),
    )
    return (resp.text or "").strip().split("\n")[0].strip()[:255]


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Fallback if model wraps JSON in markdown fences."""
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if not m:
        raise json.JSONDecodeError("No JSON object", raw, 0)
    return json.loads(m.group(0))
