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


def parse_drug_detail(html: str, *, slug: str) -> dict[str, str]:
    name = _slug_to_title(slug)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if h1:
        cleaned = re.sub(r"<[^>]+>", " ", h1.group(1))
        name = re.sub(r"\s+", " ", cleaned).strip() or name
        if "(" in name:
            name = name.split("(", 1)[0].strip()

    description = ""
    dosage = ""
    for label, field in (("Показания к применению", "description"), ("Фармакологическое действие", "description")):
        m = re.search(
            rf">{label}<[\s\S]{{0,600}}?<p[^>]*>(.*?)</p>",
            html,
            re.I,
        )
        if m and field == "description" and not description:
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            description = re.sub(r"\s+", " ", text).strip()[:2000]

    m_form = re.search(
        r"Лекарственная форма[\s\S]{0,600}?<p[^>]*>(.*?)</p>",
        html,
        re.I,
    )
    if m_form:
        text = re.sub(r"<[^>]+>", " ", m_form.group(1))
        dosage = re.sub(r"\s+", " ", text).strip()[:255]

    return {"name": name[:255], "description": description, "dosage": dosage}


def drug_item_from_slug(
    slug: str,
    *,
    detail: dict[str, str] | None = None,
) -> dict[str, Any]:
    detail = detail or {}
    name = (detail.get("name") or _slug_to_title(slug)).strip()
    return {
        "name": name[:255],
        "description": (detail.get("description") or f"Источник: vidal.ru/drugs/{slug}")[:2000],
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
