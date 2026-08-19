"""Split drug description/instructions into Vidal-like spoiler sections."""

from __future__ import annotations

import re
from typing import Any

from .utils import clean_display_text, extract_drug_mnn

# Order matches Vidal.ru card (spoilers in the app).
SECTION_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("composition", "Форма выпуска, упаковка и состав", ("форма выпуска, упаковка и состав", "форма выпуска", "состав", "лекарственная форма")),
    ("clinical_group", "Клинико-фармакологическая группа", ("клинико-фармакологич", "клинико-фармакологическая группа")),
    ("pharma_group", "Фармако-терапевтическая группа", ("фармако-терапевтическая группа", "фармакотерапевтическая группа")),
    ("action", "Фармакологическое действие", ("фармакологическое действие",)),
    ("pharmacokinetics", "Фармакокинетика", ("фармакокинетика",)),
    ("indications", "Показания препарата", ("показания препарата", "показания к применению", "показания")),
    ("dosing", "Режим дозирования", ("режим дозирования", "способ применения и дозы", "способ применения", "дозирование")),
    ("side_effects", "Побочное действие", ("побочное действие", "побочные эффекты")),
    ("contraindications", "Противопоказания к применению", ("противопоказания к применению", "противопоказания")),
    ("special", "Особые указания", ("особые указания",)),
    ("interactions", "Лекарственное взаимодействие", ("лекарственное взаимодействие", "взаимодействие")),
    ("pregnancy", "Применение при беременности и кормлении грудью", ("применение при беременности",)),
    ("contacts", "Контакты / производитель", ("контакты", "владелец регистрационного удостоверения", "производитель")),
)

_HEADER_ALIASES: dict[str, str] = {}
for key, _title, aliases in SECTION_DEFS:
    for alias in aliases:
        _HEADER_ALIASES[alias.casefold()] = key

_ALIASES_SORTED = sorted(
    (alias for _key, _title, aliases in SECTION_DEFS for alias in aliases),
    key=len,
    reverse=True,
)
_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*)?("
    + "|".join(re.escape(alias) for alias in _ALIASES_SORTED)
    + r")\s*:?\s*",
    re.IGNORECASE,
)


def _norm_header(raw: str) -> str | None:
    key = re.sub(r"\s+", " ", (raw or "").strip().rstrip(":").casefold())
    if key in _HEADER_ALIASES:
        return _HEADER_ALIASES[key]
    for alias, mapped in _HEADER_ALIASES.items():
        if key.startswith(alias) or alias.startswith(key):
            return mapped
    return None


def parse_labeled_blocks(text: str) -> dict[str, str]:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return {}
    matches = list(_HEADER_RE.finditer(raw))
    if not matches:
        return {}
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        mapped = _norm_header(m.group(1))
        if not mapped:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        chunk = clean_display_text(raw[start:end])
        if len(chunk) < 8:
            continue
        prev = out.get(mapped, "")
        out[mapped] = f"{prev} {chunk}".strip() if prev else chunk
    return out


def build_drug_sections(
    *,
    name: str = "",
    description: str = "",
    instructions: str = "",
    dosage: str = "",
    stored: list[dict[str, Any]] | dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """
    FE spoilers: [{key, title, text}, ...] — only non-empty.
    Prefer already stored structured sections, then parse labeled text.
    """
    by_key: dict[str, str] = {}
    if isinstance(stored, list):
        for row in stored:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "").strip()
            text = clean_display_text(str(row.get("text") or ""))
            if key and text:
                by_key[key] = text
    elif isinstance(stored, dict):
        for key, text in stored.items():
            t = clean_display_text(str(text or ""))
            if key and t:
                by_key[str(key)] = t

    for blob in (instructions, description):
        for key, text in parse_labeled_blocks(blob).items():
            if key not in by_key or len(text) > len(by_key[key]):
                by_key[key] = text

    dosage_c = clean_display_text(dosage)
    if dosage_c and "composition" not in by_key:
        by_key["composition"] = dosage_c

    desc_c = clean_display_text(description)
    mnn = extract_drug_mnn(description)
    extras: list[tuple[str, str, str]] = []
    if mnn:
        extras.append(("inn", "МНН", mnn))
    src = ""
    m_src = re.search(r"Источник:\s*([^\n.]+)", description or "", re.I)
    if m_src:
        src = clean_display_text(m_src.group(1))
    if src:
        extras.append(("source", "Источник", src))

    if desc_c and "action" not in by_key and "indications" not in by_key:
        # Unlabeled GRLS/Vidal blurb — still show as description spoiler.
        extras.append(("description", "Описание", desc_c))

    instr_c = clean_display_text(instructions)
    if instr_c and not parse_labeled_blocks(instructions) and "dosing" not in by_key:
        extras.append(("instructions", "Инструкция по применению", instr_c))

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, title, _aliases in SECTION_DEFS:
        text = by_key.get(key) or ""
        if not text:
            continue
        out.append({"key": key, "title": title, "text": text})
        seen.add(key)
    for key, title, text in extras:
        if key in seen or not text:
            continue
        out.append({"key": key, "title": title, "text": text})
        seen.add(key)
    return out
