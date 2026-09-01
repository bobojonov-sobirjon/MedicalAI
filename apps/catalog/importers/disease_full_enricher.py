"""Fill Disease.instructions with full spoiler sections (AI + optional Wikipedia)."""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import quote

import requests

from apps.catalog.disease_sections import (
    DISEASE_SECTION_DEFS,
    build_disease_sections,
    disease_core_name,
    fallback_disease_labeled,
)
from apps.catalog.utils import clean_display_text

logger = logging.getLogger(__name__)

WIKI_UA = "MedicAI-DiseaseEnricher/1.0 (https://medic-ai.ru; catalog enrichment)"
MKB_STUB_RE = re.compile(r"(?i)^МКБ-10:\s*\S+")


def is_stub_disease(*, description: str, instructions: str, min_instr: int = 250) -> bool:
    instr = (instructions or "").strip()
    if len(instr) >= min_instr:
        return False
    desc = clean_display_text(description or "")
    if not desc:
        return True
    if MKB_STUB_RE.match(desc) and len(desc) < 120:
        return True
    if "Код диагноза по Международной классификации" in desc:
        return True
    return len(desc) < 120 and len(instr) < min_instr


def _wiki_search_titles(name: str) -> list[str]:
    raw = (name or "").strip()
    core = disease_core_name(raw)
    out = [core, raw] if core != raw else [raw]
    cleaned = re.sub(
        r"(?i)\s*(неуточненн\w*|других локализаций|множественн\w*|острый|хронический)\s*",
        " ",
        core,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;—–-")
    if cleaned and cleaned not in out:
        out.append(cleaned)
    firsts = cleaned.split()
    if len(firsts) >= 2:
        short = " ".join(firsts[:3])
        if short not in out:
            out.append(short)
    return [x for x in out if len(x) >= 3]


def fetch_wikipedia_ru(name: str) -> str:
    """Best-effort plain extract from Russian Wikipedia."""
    session = requests.Session()
    session.headers.update({"User-Agent": WIKI_UA, "Accept-Language": "ru"})
    for title in _wiki_search_titles(name):
        got = _wiki_extract(session, title)
        if got:
            return got
    return ""


def _wiki_extract(session: requests.Session, title: str) -> str:
    try:
        # opensearch → best title
        r = session.get(
            "https://ru.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": title,
                "limit": 5,
                "namespace": 0,
                "format": "json",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        candidates = list(data[1]) if isinstance(data, list) and len(data) > 1 else []
        pick = ""
        title_l = title.casefold()
        for c in candidates:
            if c.casefold() == title_l or title_l in c.casefold() or c.casefold() in title_l:
                pick = c
                break
        if not pick and candidates:
            # first token overlap
            tok = title_l.split()[0]
            for c in candidates:
                if tok in c.casefold():
                    pick = c
                    break
        if not pick:
            pick = title

        r2 = session.get(
            "https://ru.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "exintro": 0,
                "exchars": 3500,
                "titles": pick,
                "format": "json",
                "redirects": 1,
            },
            timeout=25,
        )
        r2.raise_for_status()
        pages = (r2.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            if page.get("missing"):
                continue
            extract = clean_display_text(page.get("extract") or "")
            if len(extract) >= 120:
                return extract[:5000]
    except requests.RequestException as exc:
        logger.warning("wikipedia fetch failed for %s: %s", title, exc)
    return ""


def generate_disease_sections_ai(
    *,
    name: str,
    mkb_hint: str = "",
    wiki_text: str = "",
) -> dict[str, str]:
    from apps.catalog.disease_sections import parse_disease_labeled_blocks
    from apps.core.rutronix import chat_completions, generate_json, _assistant_text_from_message

    keys = [k for k, _t, _a in DISEASE_SECTION_DEFS]
    system = (
        "Ты медицинский редактор справочника для пациентов (RU). "
        "Пиши понятным русским языком, без HTML и без Markdown. "
        "Это справочная информация, не заменяет очную консультацию врача. "
        "Не выдумывай редкие факты; если данных мало — пиши кратко и осторожно."
    )
    user_json = (
        f"Заболевание/состояние: {name}\n"
        f"Код МКБ (если есть): {mkb_hint or '—'}\n"
        f"Доп. текст (Wikipedia, может быть пустым):\n{(wiki_text or '—')[:3000]}\n\n"
        "Верни ТОЛЬКО JSON-объект (без ```), ключи строго:\n"
        + ", ".join(keys)
        + "\nЗначения — строки на русском (2–8 предложений где уместно)."
    )
    out: dict[str, str] = {}
    try:
        data = generate_json(system, user_json, temperature=0.2)
        if isinstance(data, dict):
            for key, _title, _a in DISEASE_SECTION_DEFS:
                val = data.get(key)
                if isinstance(val, str):
                    text = clean_display_text(val)
                    if len(text) >= 40:
                        out[key] = text[:4000]
    except Exception as exc:
        logger.warning("AI JSON enrich failed for %s: %s", name, exc)

    if len(out) >= 2:
        return out

    # Fallback: labeled plain text
    user_txt = (
        f"Заболевание: {name}\nМКБ: {mkb_hint or '—'}\n"
        f"Контекст:\n{(wiki_text or '—')[:2500]}\n\n"
        "Напиши справочный текст строго в формате:\n\n"
        + "\n\n".join(f"{title}\n..." for _k, title, _a in DISEASE_SECTION_DEFS)
    )
    try:
        resp = chat_completions(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_txt},
            ],
            temperature=0.25,
            max_completion_tokens=3500,
        )
        raw = _assistant_text_from_message((resp.get("choices") or [{}])[0].get("message") or {})
        labeled = parse_disease_labeled_blocks(raw)
        for key, text in labeled.items():
            if len(text) >= 40:
                out[key] = text[:4000]
    except Exception as exc:
        logger.warning("AI text enrich failed for %s: %s", name, exc)

    return out


def sections_to_instructions(labeled: dict[str, str]) -> tuple[str, str]:
    sections = build_disease_sections(description="", instructions="", stored=labeled)
    instructions = "\n\n".join(f"{row['title']}\n{row['text']}" for row in sections)[:30000]
    description = (
        labeled.get("overview")
        or labeled.get("symptoms")
        or labeled.get("causes")
        or (sections[0]["text"] if sections else "")
    )[:2000]
    return instructions, description


def enrich_one_disease(
    *,
    name: str,
    description: str = "",
    use_wikipedia: bool = True,
    use_ai: bool = True,
) -> dict[str, Any] | None:
    mkb = ""
    m = re.search(r"(?i)МКБ-10:\s*([A-ZА-Я]\d[\w.]*)", description or "")
    if m:
        mkb = m.group(1)

    wiki = fetch_wikipedia_ru(name) if use_wikipedia else ""
    labeled: dict[str, str] = {}

    if use_ai:
        try:
            labeled = generate_disease_sections_ai(name=name, mkb_hint=mkb, wiki_text=wiki)
        except Exception as exc:
            logger.warning("AI enrich failed for %s: %s", name, exc)
            labeled = {}

    if not labeled and wiki:
        labeled = {"overview": wiki[:4000], **{k: v for k, v in fallback_disease_labeled(name).items() if k != "overview"}}
        labeled["overview"] = wiki[:4000]

    if not labeled:
        labeled = fallback_disease_labeled(name)

    instructions, desc = sections_to_instructions(labeled)
    if len(instructions) < 80:
        return None
    return {
        "description": desc,
        "instructions": instructions,
        "sections": labeled,
        "source": ("ai+wiki" if (use_ai and wiki) else "wiki" if wiki else "fallback"),
    }
