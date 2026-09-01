"""Split drug description/instructions into Vidal-like spoiler sections."""

from __future__ import annotations

import re
from typing import Any

from .utils import (
    clean_display_text,
    extract_drug_mnn,
    format_section_markdown,
    is_junk_scraped_text,
    is_registry_meta_text,
)

# Order matches Vidal.ru card (spoilers in the app).
SECTION_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("composition", "Форма выпуска, упаковка и состав", ("форма выпуска, упаковка и состав", "форма выпуска", "лекарственная форма")),
    ("clinical_group", "Клинико-фармакологическая группа", ("клинико-фармакологич", "клинико-фармакологическая группа", "групповая принадлежность")),
    ("pharma_group", "Фармако-терапевтическая группа", ("фармако-терапевтическая группа", "фармакотерапевтическая группа")),
    ("action", "Фармакологическое действие", ("фармакологическое действие", "свойства")),
    ("pharmacokinetics", "Фармакокинетика", ("фармакокинетика",)),
    ("indications", "Показания препарата", ("показания препарата", "показания к применению", "область применения")),
    ("dosing", "Режим дозирования", ("режим дозирования", "способ применения и дозы", "способ применения", "рекомендации по применению", "дозирование")),
    ("side_effects", "Побочное действие", ("побочное действие", "побочные эффекты")),
    ("contraindications", "Противопоказания к применению", ("противопоказания к применению", "противопоказания")),
    ("special", "Особые указания", ("особые указания",)),
    ("interactions", "Лекарственное взаимодействие", ("лекарственное взаимодействие",)),
    ("pregnancy", "Применение при беременности и кормлении грудью", ("применение при беременности и в период лактации", "применение при беременности")),
    ("dispensing", "Условия реализации", ("условия реализации",)),
    ("storage", "Условия хранения", ("условия хранения",)),
    ("shelf_life", "Срок годности", ("срок годности",)),
    ("contacts", "Контакты / производитель", ("контакты для обращений", "владелец регистрационного удостоверения")),
)

# Mid-string splitters: full titles only (short aliases like «состав» false-split).
_SPLIT_TITLES: tuple[str, ...] = tuple(
    sorted(
        {
            *(title for _k, title, _a in SECTION_DEFS),
            "Форма выпуска, упаковка и состав",
            "Клинико-фармакологическая группа",
            "Фармако-терапевтическая группа",
            "Фармакологическое действие",
            "Фармакокинетика",
            "Показания препарата",
            "Показания к применению",
            "Режим дозирования",
            "Способ применения и дозы",
            "Побочное действие",
            "Противопоказания к применению",
            "Противопоказания",
            "Особые указания",
            "Лекарственное взаимодействие",
            "Применение при беременности и кормлении грудью",
            "Применение при беременности и в период лактации",
            "Контакты / производитель",
            "Контакты для обращений",
            "Групповая принадлежность",
            "Область применения",
            "Рекомендации по применению",
            "Условия хранения",
            "Срок годности",
            "Условия реализации",
            "Свойства",
        },
        key=len,
        reverse=True,
    )
)

_HEADER_ALIASES: dict[str, str] = {}
for key, _title, aliases in SECTION_DEFS:
    _HEADER_ALIASES[_title.casefold()] = key
    for alias in aliases:
        _HEADER_ALIASES[alias.casefold()] = key

_ALIASES_SORTED = sorted(_HEADER_ALIASES.keys(), key=len, reverse=True)
_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*)?(?<![А-Яа-яЁёA-Za-z])("
    + "|".join(re.escape(alias) for alias in _ALIASES_SORTED)
    + r")(?![А-Яа-яЁёA-Za-z])\s*:?\s*",
    re.IGNORECASE,
)
_PRODUCT_SUFFIX_RE = re.compile(r"(?i)\s+продукта\s+\S.*$")


def _norm_header(raw: str) -> str | None:
    key = re.sub(r"\s+", " ", (raw or "").strip().rstrip(":").casefold())
    key = _PRODUCT_SUFFIX_RE.sub("", key).strip()
    if key in _HEADER_ALIASES:
        return _HEADER_ALIASES[key]
    for alias, mapped in _HEADER_ALIASES.items():
        if len(alias) >= 12 and (key.startswith(alias) or alias.startswith(key)):
            return mapped
    return None


def _ensure_title_newlines(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n")
    for title in _SPLIT_TITLES:
        raw = re.sub(
            rf"(?<!\n)(?<![А-Яа-яЁёA-Za-z])({re.escape(title)})",
            r"\n\1",
            raw,
            flags=re.IGNORECASE,
        )
    return raw


def parse_labeled_blocks(text: str) -> dict[str, str]:
    raw = _ensure_title_newlines(text).strip()
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
        chunk = format_section_markdown(raw[start:end])
        if len(chunk) < 8 or is_junk_scraped_text(chunk):
            continue
        prev = out.get(mapped, "")
        out[mapped] = f"{prev}\n\n{chunk}".strip() if prev else chunk
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
    FE spoilers: [{key, title, text}, ...] — only non-empty Markdown.
    Prefer already stored structured sections, then parse labeled text.
    """
    if is_registry_meta_text(description):
        description = ""
    if is_registry_meta_text(instructions):
        instructions = ""

    by_key: dict[str, str] = {}
    if isinstance(stored, list):
        for row in stored:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "").strip()
            text = format_section_markdown(str(row.get("text") or ""))
            if key and text and not is_junk_scraped_text(text):
                by_key[key] = text
    elif isinstance(stored, dict):
        for key, text in stored.items():
            t = format_section_markdown(str(text or ""))
            if key and t and not is_junk_scraped_text(t):
                by_key[str(key)] = t

    for blob in (instructions, description):
        for key, text in parse_labeled_blocks(blob).items():
            if key not in by_key and text and not is_registry_meta_text(text):
                by_key[key] = text

    by_key = {
        k: v
        for k, v in by_key.items()
        if v and not is_junk_scraped_text(v) and not is_registry_meta_text(v)
    }

    dosage_c = format_section_markdown(dosage)
    if dosage_c and "composition" not in by_key:
        by_key["composition"] = dosage_c

    desc_c = format_section_markdown(description)
    mnn = extract_drug_mnn(description) or extract_drug_mnn(instructions)
    extras: list[tuple[str, str, str]] = []
    if mnn:
        extras.append(("inn", "МНН", mnn))
    src = ""
    m_src = re.search(r"Источник:\s*([^\n.]+)", description or "", re.I)
    if m_src:
        src = clean_display_text(m_src.group(1))
    if src and "vidal" not in src.casefold() and "грлс" not in src.casefold():
        extras.append(("source", "Источник", src))

    if (
        desc_c
        and not is_registry_meta_text(desc_c)
        and "action" not in by_key
        and "indications" not in by_key
    ):
        extras.append(("description", "Описание", desc_c))

    instr_c = format_section_markdown(instructions)
    if (
        instr_c
        and not is_registry_meta_text(instr_c)
        and not parse_labeled_blocks(instructions)
        and "dosing" not in by_key
    ):
        extras.append(("instructions", "Инструкция по применению", instr_c))

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, title, _aliases in SECTION_DEFS:
        text = by_key.get(key) or ""
        if not text or is_junk_scraped_text(text) or is_registry_meta_text(text):
            continue
        out.append({"key": key, "title": title, "text": text})
        seen.add(key)
    for key, title, text in extras:
        if key in seen or not text:
            continue
        if key in {"description", "instructions", "inn", "source"}:
            if is_registry_meta_text(text):
                continue
        if key == "source" and "грлс" in text.casefold():
            continue
        if key not in {"inn", "source"} and (
            is_junk_scraped_text(text) or is_registry_meta_text(text)
        ):
            continue
        out.append({"key": key, "title": title, "text": text})
        seen.add(key)
    if len(out) < 3:
        fallback = fallback_drug_labeled(name=name, dosage=dosage, inn=mnn)
        titles = {k: t for k, t, _a in SECTION_DEFS}
        for key, text in fallback.items():
            if key in seen or not text:
                continue
            out.append({"key": key, "title": titles.get(key) or key, "text": text})
            seen.add(key)
        out.sort(
            key=lambda row: next(
                (i for i, (k, _t, _a) in enumerate(SECTION_DEFS) if k == row["key"]),
                99,
            )
        )
    return out


def fallback_drug_overview(*, name: str, dosage: str = "", inn: str = "") -> str:
    title = (name or "Препарат").strip()
    bits: list[str] = [f"{title} — лекарственное средство (или БАД) из справочника."]
    if inn:
        bits.append(f"Действующее вещество (МНН): {inn}.")
    if dosage:
        bits.append(f"Форма / дозировка: {dosage.strip()}.")
    bits.append(
        "Ниже в карточке — сведения из инструкции: состав, показания, как принимать, "
        "побочные эффекты и противопоказания. Это справочная информация, она не заменяет "
        "очную консультацию и не является назначением."
    )
    bits.append(
        "Дозу и длительность курса определяет врач. Не начинайте приём по совету из интернета, "
        "не давайте препарат детям без назначения. При аллергии, беременности, кормлении грудью "
        "или хронических болезнях сначала уточните возможность применения у специалиста."
    )
    bits.append(
        "Срочно обратитесь за помощью при отёке, сыпи, затруднении дыхания, сильной слабости "
        "или других тревожных симптомах после приёма."
    )
    return " ".join(bits)


def fallback_drug_labeled(*, name: str, dosage: str = "", inn: str = "") -> dict[str, str]:
    overview = fallback_drug_overview(name=name, dosage=dosage, inn=inn)
    labeled: dict[str, str] = {
        "action": overview,
        "indications": (
            f"{name} применяют по показаниям, указанным в официальной инструкции и назначению врача. "
            "Не используйте препарат «на всякий случай» и не повторяйте чужие схемы."
        ),
        "dosing": (
            "Режим дозирования индивидуален. Ориентируйтесь на назначение врача и лист-вкладыш: "
            "возраст, масса тела, сопутствующие болезни и другие лекарства влияют на дозу. "
            "Не увеличивайте дозу самостоятельно."
        ),
        "contraindications": (
            "Типичные ограничения: индивидуальная непереносимость компонентов, ряд состояний "
            "по инструкции (в том числе беременность и детский возраст — если указано). "
            "Полный список — у врача и в инструкции к упаковке."
        ),
        "special": (
            "Храните в недоступном для детей месте, соблюдайте срок годности. "
            "Информация в приложении упрощена для пациента и может быть неполной."
        ),
    }
    if dosage:
        labeled["composition"] = dosage.strip()
    if inn:
        labeled["clinical_group"] = f"МНН: {inn}"
    return labeled


def compose_drug_description(
    *,
    name: str = "",
    description: str = "",
    instructions: str = "",
    dosage: str = "",
    inn: str = "",
    sections: list[dict[str, str]] | None = None,
) -> str:
    """Long patient-facing blurb under the drug title (several paragraphs)."""
    rows = (
        sections
        if sections is not None
        else build_drug_sections(
            name=name,
            description=description,
            instructions=instructions,
            dosage=dosage,
        )
    )
    order = (
        "action",
        "indications",
        "clinical_group",
        "dosing",
    )
    by_key = {r["key"]: r["text"] for r in rows if r.get("key") and r.get("text")}
    paras: list[str] = []
    seen: set[str] = set()
    for key in order:
        raw = by_key.get(key) or ""
        flat = re.sub(r"\s+", " ", raw).strip()
        if len(flat) < 24:
            continue
        if len(flat) > 420:
            cut = flat[:420]
            dot = cut.rfind(".")
            if dot >= 120:
                flat = cut[: dot + 1]
            else:
                flat = cut.rstrip() + "…"
        keyn = flat[:160].casefold()
        if any(keyn in s or s in keyn for s in seen):
            continue
        seen.add(keyn)
        paras.append(flat)
        if len(paras) >= 4:
            break
    text = "\n\n".join(paras).strip()
    if len(re.sub(r"\s+", "", text)) < 80:
        text = fallback_drug_overview(name=name, dosage=dosage, inn=inn)
    from .utils import clean_drug_plain_text

    return clean_drug_plain_text(text)[:4000]
