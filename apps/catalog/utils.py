from __future__ import annotations

import re

_PREVIEW_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def description_preview(text: str, *, max_chars: int = 320) -> str:
    """First ~3 lines for mobile cards («Подробнее» opens full description)."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
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
