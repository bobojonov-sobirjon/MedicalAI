"""TZ §5.7.1 — грубый фильтр матов (расширяйте список)."""

from __future__ import annotations

_BAD = frozenset(
    x.lower()
    for x in (
        "хуй",
        "пизд",
        "ебан",
        "бля",
        "сука",
        "мудак",
    )
)


def contains_profanity(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in _BAD)
