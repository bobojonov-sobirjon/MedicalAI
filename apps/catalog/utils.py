from __future__ import annotations

import html
import re

_PREVIEW_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_display_text(text: str) -> str:
    """Decode HTML entities (&reg; → ®) and strip leftover tags for mobile UI."""
    raw = html.unescape((text or "").replace("\xa0", " "))
    raw = _HTML_TAG_RE.sub("", raw)
    return re.sub(r"\s+", " ", raw).strip()



_LATIN_BRACKET_RE = re.compile(r"\s*\[[^\[\]]*[A-Za-z][^\[\]]*\]")
_PAREN_RE = re.compile(r"\s*\(([^)]*)\)")
_MNN_RE = re.compile(r"МНН:\s*([^.\n;]+)", re.IGNORECASE)
_LATIN_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s\-/',.+]*$")


def clean_disease_display_name(name: str) -> str:
    """Убрать английские пояснения вида [herpes simplex], оставить коды МКБ (G05.1*)."""
    raw = re.sub(r"\s+", " ", (name or "").strip())
    if not raw:
        return ""
    cleaned = _LATIN_BRACKET_RE.sub("", raw)

    def _keep_or_drop_paren(match: re.Match[str]) -> str:
        inner = (match.group(1) or "").strip()
        if not inner:
            return ""
        # Коды МКБ / с цифрами — оставляем.
        if re.search(r"\d", inner):
            return match.group(0)
        if re.search(r"[А-Яа-яЁё]", inner):
            return match.group(0)
        if _LATIN_ONLY_RE.match(inner):
            return ""
        return match.group(0)

    cleaned = _PAREN_RE.sub(_keep_or_drop_paren, cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;—–-")
    return cleaned if cleaned else raw


def extract_drug_mnn(description: str) -> str:
    """Достать МНН из описания ГРЛС: 'МНН: Валацикловир. ...'."""
    match = _MNN_RE.search(description or "")
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip().casefold()


def split_mnn_parts(mnn: str) -> list[str]:
    """Разбить комбо-МНН: 'метформин+глибенкламид' → ['метформин', 'глибенкламид']."""
    raw = (mnn or "").casefold().strip()
    if not raw:
        return []
    parts = re.split(r"[+/;,|]+|\s+и\s+", raw)
    out: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip(" .")
        if len(part) < 3:
            continue
        # Убрать дозировки вида «500 мг»
        part = re.sub(r"\b\d+[.,]?\d*\s*(мг|г|мл|%|ме)\b", "", part, flags=re.I).strip()
        if len(part) >= 3:
            out.append(part)
    return out or ([raw] if len(raw) >= 3 else [])


def description_preview(text: str, *, max_chars: int = 320) -> str:
    """First ~3 lines for mobile cards («Подробнее» opens full description)."""
    raw = clean_display_text(text)
    if not raw:
        return ""
    if len(raw) <= max_chars:
        return raw

    sentences = _PREVIEW_SENTENCE_RE.split(raw)
    preview = ""
    for sentence in sentences:
        candidate = f"{preview} {sentence}".strip() if preview else sentence.strip()
        if len(candidate) > max_chars and preview:
            break
        preview = candidate
        if len(preview) >= max_chars * 0.55 and preview.count(".") + preview.count("!") + preview.count("?") >= 2:
            break

    if not preview:
        preview = raw[: max_chars - 1].rstrip() + "…"
    elif len(raw) > len(preview):
        preview = preview.rstrip(".,;:!? ") + "…"
    return preview
