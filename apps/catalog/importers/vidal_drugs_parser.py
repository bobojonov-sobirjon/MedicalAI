"""Vidal.ru drug catalog parser for Drug model."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests

from .catalog_json import load_catalog_json, save_catalog_json

logger = logging.getLogger(__name__)

VIDAL_BASE = "https://www.vidal.ru"
VIDAL_PRODUCTS = f"{VIDAL_BASE}/drugs/products"
USER_AGENT = "MedicAI-VidalDrugs-Importer/1.0 (+https://medic-ai.ru; TZ catalog)"

NON_DRUG_SLUGS = frozenset(
    {
        "products",
        "molecules",
        "clinic-pointers",
        "pharm-groups",
        "clinic-groups",
        "nosology",
        "atc",
        "companies",
        "disease",
        "parapharm",
        "advanced",
        "new",
        "search",
        "analog",
    }
)

DRUG_SLUG_RE = re.compile(r'href="(/drugs/([a-z0-9][a-z0-9\-]{1,120}))"', re.IGNORECASE)
LETTER_PAGE_RE = re.compile(r'href="(/drugs/products/p/rus-[^"]+)"', re.IGNORECASE)


@dataclass
class VidalDrugsParseStats:
    pages_processed: int = 0
    drugs_total: int = 0
    details_fetched: int = 0
    errors: list[str] = field(default_factory=list)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
    return session


def _fetch(session: requests.Session, url: str, *, timeout: int = 30) -> str | None:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        logger.warning("vidal fetch failed %s: %s", url, exc)
        return None


def _is_drug_slug(slug: str) -> bool:
    slug = slug.strip().lower()
    if not slug or slug in NON_DRUG_SLUGS:
        return False
    if slug.startswith("products") or "/" in slug:
        return False
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,120}", slug))


def _slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").strip().title()


def discover_letter_pages(session: requests.Session) -> list[str]:
    html = _fetch(session, VIDAL_PRODUCTS)
    if not html:
        return [f"{VIDAL_BASE}/drugs/products/p/rus-{ch}" for ch in "абвгдежзийклмнопрстуфхцчшщэюя"]
    pages = sorted({urljoin(VIDAL_BASE, m.group(1)) for m in LETTER_PAGE_RE.finditer(html)})
    return pages


def extract_drug_slugs_from_html(html: str) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    for _href, slug in DRUG_SLUG_RE.findall(html):
        key = slug.lower()
        if not _is_drug_slug(slug) or key in seen:
            continue
        seen.add(key)
        slugs.append(slug)
    return slugs


def _html_fragment_to_markdown(html: str) -> str:
    import html as html_lib

    from apps.catalog.utils import format_section_markdown

    text = html or ""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)

    def _table_to_md(match: re.Match[str]) -> str:
        table_html = match.group(0)
        rows: list[list[str]] = []
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", table_html):
            cells = re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)
            cleaned = [
                html_lib.unescape(re.sub(r"<[^>]+>", " ", c))
                for c in cells
            ]
            cleaned = [re.sub(r"\s+", " ", c).strip() for c in cleaned]
            if any(cleaned):
                rows.append(cleaned)
        if not rows:
            return "\n"
        if all(len(r) == 2 for r in rows):
            head_a, head_b = rows[0]
            lines = []
            if head_a:
                lines.append(f"**{head_a}**" + (f" ({head_b})" if head_b else ""))
            for a, b in rows[1:]:
                if a and b:
                    lines.append(f"- {a} — {b}")
                elif a:
                    lines.append(f"- {a}")
            return "\n" + "\n".join(lines) + "\n"
        return "\n" + "\n".join(" — ".join(c for c in row if c) for row in rows) + "\n"

    text = re.sub(r"(?is)<table[^>]*>.*?</table>", _table_to_md, text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    from apps.catalog.utils import format_section_markdown

    return format_section_markdown(text)


def _strip_product_suffix(title: str) -> str:
    title = re.sub(r"<[^>]+>", " ", title or "")
    title = re.sub(r"\s+", " ", title).strip(" :")
    title = re.sub(r"(?i)\s+продукта\s+\S.*$", "", title).strip(" :")
    return title


def _cut_ads_html(html: str) -> str:
    return re.split(
        r'(?is)<div[^>]*class="[^"]*\bmkb\b|<style\b|<script\b|'
        r'<div[^>]*id="yandex|<div[^>]*class="[^"]*\byad\b|'
        r"<!--noindex-->|<div[^>]*class=\"share-buttons\"|"
        r'<div[^>]*id="banners"|проверено врачом|id="validated"|class="footer',
        html or "",
        maxsplit=1,
    )[0]


_BLOCK_HEAD_RE = re.compile(
    r'(?is)<(?:h2|div|span)[^>]*class="[^"]*\bblock-head\b[^"]*"[^>]*>(.*?)</(?:h2|div|span)>'
)


def extract_vidal_blocks(html: str) -> dict[str, str]:
    """Pull only .block-head + following content; skip ads/scripts/MKB tables."""
    from apps.catalog.instruction_sections import _norm_header

    raw = html or ""
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    parts = _BLOCK_HEAD_RE.split(raw)
    labeled: dict[str, str] = {}
    i = 1
    while i < len(parts):
        title = _strip_product_suffix(parts[i])
        body_html = _cut_ads_html(parts[i + 1] if i + 1 < len(parts) else "")
        i += 2
        if re.search(r"(?i)мкб|открыть список", title):
            continue
        body = _html_fragment_to_markdown(body_html)
        mapped = _norm_header(title)
        if not mapped:
            if re.search(r'(?i)infopage|info-pages|алтайвитамин|произведен', body_html + title):
                mapped = "contacts"
                if title and title.casefold() not in {"контакты для обращений", "контакты"}:
                    body = f"**{title}**\n\n{body}".strip() if body else f"**{title}**"
            else:
                continue
        if len(body) < 8:
            continue
        if mapped == "contacts":
            prev = labeled.get("contacts", "")
            labeled["contacts"] = _merge_contact_text(prev, body)
            continue
        prev = labeled.get(mapped, "")
        labeled[mapped] = f"{prev}\n\n{body}".strip() if prev else body
    return labeled


def _merge_contact_text(prev: str, incoming: str) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    for part in f"{prev}\n{incoming}".split("\n"):
        key = re.sub(r"\s+", " ", part).strip().casefold()
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        chunks.append(part.strip())
    return "\n".join(chunks).strip()


def _html_to_text(html: str) -> str:
    from apps.catalog.utils import clean_display_text

    text = html or ""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)
    text = re.sub(r'(?is)<div[^>]*class="[^"]*\bmkb\b[^"]*"[^>]*>.*?</div>', " ", text)
    text = re.sub(r'(?is)<div[^>]*id="yandex_rtb[^"]*"[^>]*>.*?</div>', " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|section)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_display_text(text)


def _extract_labeled_paragraph(html: str, label: str) -> str:
    m = re.search(
        rf">{re.escape(label)}<[\s\S]{{0,4000}}?<p[^>]*>(.*?)</p>",
        html,
        re.I,
    )
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", text).strip()


def parse_drug_detail(html: str, *, slug: str) -> dict[str, Any]:
    from apps.catalog.instruction_sections import SECTION_DEFS, build_drug_sections, parse_labeled_blocks
    from apps.catalog.utils import flatten_display_text, format_section_markdown

    name = _slug_to_title(slug)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if h1:
        cleaned = re.sub(r"<[^>]+>", " ", h1.group(1))
        name = re.sub(r"\s+", " ", cleaned).strip() or name
        if "(" in name:
            name = name.split("(", 1)[0].strip()

    labeled = extract_vidal_blocks(html)
    if len(labeled) < 2:
        plain = _html_to_text(html)
        from_blocks = parse_labeled_blocks(plain)
        for key, text in from_blocks.items():
            if key not in labeled or len(text) > len(labeled[key]):
                labeled[key] = text
    if len(labeled) < 2:
        for key, title, aliases in SECTION_DEFS:
            if labeled.get(key):
                continue
            for alias in (title, *aliases):
                chunk = _extract_labeled_paragraph(html, alias)
                if chunk:
                    labeled[key] = format_section_markdown(chunk)
                    break

    sections = build_drug_sections(
        name=name,
        description="",
        instructions="",
        dosage=labeled.get("composition", ""),
        stored=labeled,
    )
    instructions = "\n\n".join(f"{row['title']}\n{row['text']}" for row in sections)[:20000]
    description = flatten_display_text(
        labeled.get("action") or labeled.get("indications") or labeled.get("composition") or ""
    )[:4000]
    dosage = flatten_display_text(labeled.get("composition") or "")[:255]
    if not dosage:
        m_form = re.search(
            r"Лекарственная форма[\s\S]{0,800}?<p[^>]*>(.*?)</p>",
            html,
            re.I,
        )
        if m_form:
            text = re.sub(r"<[^>]+>", " ", m_form.group(1))
            dosage = flatten_display_text(text)[:255]

    return {
        "name": name[:255],
        "description": description,
        "dosage": dosage,
        "instructions": instructions,
        "sections": labeled,
    }


def drug_item_from_slug(
    slug: str,
    *,
    detail: dict[str, str] | None = None,
) -> dict[str, Any]:
    detail = detail or {}
    name = (detail.get("name") or _slug_to_title(slug)).strip()
    return {
        "name": name[:255],
        "description": (detail.get("description") or f"Источник: vidal.ru/drugs/{slug}")[:4000],
        "instructions": (detail.get("instructions") or "")[:20000],
        "dosage": (detail.get("dosage") or "")[:255],
        "external_source": "vidal",
        "external_id": slug,
        "source_url": f"{VIDAL_BASE}/drugs/{slug}",
    }


def load_vidal_parse_state(path: Path) -> dict:
    if not path.exists():
        return {"completed_pages": [], "drugs": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed_pages": [], "drugs": {}}


def save_vidal_parse_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_vidal_drugs(
    *,
    letter_pages: list[str] | None = None,
    fetch_details: bool = False,
    delay_sec: float = 0.8,
    detail_delay_sec: float = 0.5,
    limit_pages: int = 0,
    limit_details: int = 0,
    existing: dict[str, dict[str, Any]] | None = None,
    state_path: Path | None = None,
    on_page_done: Callable[[str, list[dict[str, Any]], VidalDrugsParseStats], None] | None = None,
) -> tuple[list[dict[str, Any]], VidalDrugsParseStats]:
    session = _session()
    stats = VidalDrugsParseStats()
    drugs_map = dict(existing or {})

    pages = letter_pages or discover_letter_pages(session)
    if limit_pages > 0:
        pages = pages[:limit_pages]

    state = load_vidal_parse_state(state_path) if state_path else {"completed_pages": []}
    done_pages = {p for p in state.get("completed_pages", [])}

    for page_url in pages:
        if page_url in done_pages:
            continue
        html = _fetch(session, page_url)
        stats.pages_processed += 1
        if not html:
            stats.errors.append(f"Page yuklanmadi: {page_url}")
            time.sleep(delay_sec)
            continue

        for slug in extract_drug_slugs_from_html(html):
            key = f"vidal:{slug}"
            if key not in drugs_map:
                drugs_map[key] = drug_item_from_slug(slug)

        if fetch_details:
            detail_count = 0
            for key, row in list(drugs_map.items()):
                if limit_details > 0 and stats.details_fetched >= limit_details:
                    break
                slug = str(row.get("external_id") or key.split(":", 1)[-1])
                if row.get("_detail_done"):
                    continue
                detail_html = _fetch(session, f"{VIDAL_BASE}/drugs/{slug}")
                if detail_html:
                    parsed = parse_drug_detail(detail_html, slug=slug)
                    row.update(drug_item_from_slug(slug, detail=parsed))
                    row["_detail_done"] = True
                    drugs_map[key] = row
                    stats.details_fetched += 1
                    detail_count += 1
                if detail_delay_sec > 0:
                    time.sleep(detail_delay_sec)

        if state_path:
            done_pages.add(page_url)
            state["completed_pages"] = sorted(done_pages)
            save_vidal_parse_state(state_path, state)

        stats.drugs_total = len(drugs_map)
        result = sorted(drugs_map.values(), key=lambda x: x.get("name", ""))
        if on_page_done:
            on_page_done(page_url, result, stats)
        if delay_sec > 0:
            time.sleep(delay_sec)

    final = sorted(drugs_map.values(), key=lambda x: x.get("name", ""))
    for row in final:
        row.pop("_detail_done", None)
    stats.drugs_total = len(final)
    return final, stats


def save_drugs_json(items: list[dict[str, Any]], path: Path, *, meta: dict | None = None) -> None:
    clean = []
    for row in items:
        item = dict(row)
        item.pop("_detail_done", None)
        clean.append(item)
    save_catalog_json(clean, path, entity="drug", source="vidal", meta=meta)


def load_drugs_json(path: Path) -> list[dict[str, Any]]:
    return load_catalog_json(path)
