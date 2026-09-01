"""Vidal-like disease article sections for mobile spoilers."""

from __future__ import annotations

import re
from typing import Any

from .utils import clean_display_text, format_section_markdown, is_junk_scraped_text

DISEASE_SECTION_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("overview", "Общие сведения", ("общие сведения", "общее описание", "описание")),
    ("causes", "Причины", ("причины", "этиология")),
    ("symptoms", "Симптомы", ("симптомы", "симптомы амебиаза", "клиническая картина")),
    ("complications", "Осложнения", ("осложнения", "осложнения амебиаза")),
    ("self_help", "Что можете сделать Вы", ("что можете сделать вы", "что можно сделать", "самопомощь")),
    ("treatment", "Лечение", ("лечение", "терапия")),
    ("prevention", "Профилактические меры", ("профилактические меры", "профилактика")),
    ("diagnosis", "Диагностика", ("диагностика",)),
)

_HEADER_ALIASES: dict[str, str] = {}
for key, _title, aliases in DISEASE_SECTION_DEFS:
    for alias in aliases:
        _HEADER_ALIASES[alias.casefold()] = key

_ALIASES_SORTED = sorted(_HEADER_ALIASES.keys(), key=len, reverse=True)
_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*)?("
    + "|".join(re.escape(a) for a in _ALIASES_SORTED)
    + r")\s*:?\s*",
    re.IGNORECASE,
)


def _norm_header(raw: str) -> str | None:
    key = re.sub(r"\s+", " ", (raw or "").strip().rstrip(":").casefold())
    if key in _HEADER_ALIASES:
        return _HEADER_ALIASES[key]
    for alias, mapped in _HEADER_ALIASES.items():
        if key.startswith(alias) or alias in key:
            return mapped
    return None


def parse_disease_labeled_blocks(text: str) -> dict[str, str]:
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
        chunk = format_section_markdown(raw[start:end])
        if len(chunk) < 20 or is_junk_scraped_text(chunk):
            continue
        prev = out.get(mapped, "")
        out[mapped] = f"{prev} {chunk}".strip() if prev else chunk
    return out


def build_disease_sections(
    *,
    description: str = "",
    instructions: str = "",
    stored: dict[str, str] | list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
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
        for key, text in parse_disease_labeled_blocks(blob).items():
            if key not in by_key or len(text) > len(by_key[key]):
                by_key[key] = text

    desc = format_section_markdown(description)
    if desc and "overview" not in by_key and not parse_disease_labeled_blocks(description):
        by_key.setdefault("overview", desc)

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, title, _aliases in DISEASE_SECTION_DEFS:
        text = by_key.get(key) or ""
        if not text:
            continue
        out.append({"key": key, "title": title, "text": text})
        seen.add(key)
    return out


_CAUSE_TAIL_RE = re.compile(
    r"(?i)\s*как причина болезней.*$"
    r"|\s*классифицированн\w*\s+в других рубриках.*$"
)


def disease_core_name(name: str) -> str:
    """'Escherichia coli как причина болезней…' → 'Escherichia coli'."""
    raw = re.sub(r"\s+", " ", (name or "").strip())
    core = _CAUSE_TAIL_RE.sub("", raw).strip(" ,.—–-")
    return core or raw


def is_mkb_cause_heading(name: str) -> bool:
    return bool(re.search(r"(?i)как причина болезней|в других рубриках", name or ""))


def fallback_disease_overview(name: str) -> str:
    """Patient-facing text when catalog has only an MKB stub."""
    core = disease_core_name(name)
    if is_mkb_cause_heading(name):
        return (
            f"{core} в этой рубрике означает не отдельную «бытовую» болезнь, "
            f"а причину (возбудитель или фактор), из‑за которой развилось другое заболевание — "
            f"например инфекция конкретного органа. Врач указывает такую формулировку в диагнозе, "
            f"когда подтверждена роль {core}. Симптомы, обследования и лечение зависят от того, "
            f"какой орган поражён, и подбираются индивидуально. Самолечение недопустимо; "
            f"нужна очная консультация врача. Информация справочная и не заменяет приём."
        )
    return (
        f"{name} — состояние из медицинского справочника. Ниже — краткие сведения для пациента: "
        f"что это такое, на что обратить внимание и когда обратиться к врачу. "
        f"Точный диагноз, обследования и лечение назначает врач; "
        f"текст не заменяет очную консультацию и не является руководством к самолечению."
    )


def fallback_disease_labeled(name: str) -> dict[str, str]:
    core = disease_core_name(name)
    overview = fallback_disease_overview(name)
    if is_mkb_cause_heading(name):
        return {
            "overview": overview,
            "causes": (
                f"В названии рубрики указан фактор {core}. Он может вызвать разные по локализации "
                f"заболевания (например инфекции мочевых путей, кишечника, ран, дыхательных путей — "
                f"в зависимости от возбудителя). Конкретную причину и очаг определяет врач по анализам."
            ),
            "symptoms": (
                "Симптомы зависят не от формулировки рубрики, а от поражённого органа: "
                "боль, температура, нарушения стула, мочеиспускания, кашель и т.д. "
                "Одинаковой «типичной картины» для всей рубрики нет."
            ),
            "treatment": (
                "Лечение направлено на основное заболевание и подтверждённого возбудителя/фактор. "
                "Схему (в том числе нужны ли антибиотики) выбирает только врач. "
                "Не начинайте и не отменяйте препараты самостоятельно."
            ),
            "prevention": (
                "Профилактика зависит от возбудителя: гигиена рук, безопасное питание, "
                "уход за ранами, вакцинация по календарю — по рекомендации врача."
            ),
        }
    return {
        "overview": overview,
        "causes": (
            f"Причины {core} могут быть разными (инфекция, воспаление, обменные и другие факторы). "
            f"Их выясняет врач по жалобам, осмотру и обследованиям."
        ),
        "symptoms": (
            "Проявления индивидуальны: ухудшение самочувствия, боль, температура, слабость "
            "или симптомы со стороны поражённого органа. При быстром ухудшении нужна срочная помощь."
        ),
        "treatment": (
            "Лечение подбирается после постановки диагноза. Не используйте чужие схемы "
            "и не откладывайте визит к врачу при тяжёлых симптомах."
        ),
        "prevention": (
            "Общие меры: режим, питание, отказ от самолечения, своевременное обращение за помощью. "
            "Конкретные рекомендации даёт лечащий врач."
        ),
    }
