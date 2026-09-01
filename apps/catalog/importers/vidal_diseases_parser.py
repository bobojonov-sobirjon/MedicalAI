"""Parse Vidal.ru medical encyclopedia disease articles."""

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
DISEASE_INDEX = f"{VIDAL_BASE}/drugs/disease"
USER_AGENT = "MedicAI-VidalDiseases-Importer/1.0 (+https://medic-ai.ru; TZ catalog)"

ENCY_LINK_RE = re.compile(
    r'href="(/encyclopedia/[a-z0-9][a-z0-9\-]+/[a-z0-9][a-z0-9\-]+)"',
    re.IGNORECASE,
)
# Cosmetic / promo articles to skip
SKIP_CATEGORY = frozenset({"esteticheskaya-medicina"})
SKIP_SLUG_PARTS = (
    "krem-",
    "bad-",
    "shampun",
    "make-up",
    "revlon",
    "vichy",
    "intercharm",
    "orofluido",
    "head--shoulders",
    "nyx-",
    "danone",
    "pharmanex",
    "bio-oil",
)


@dataclass
class VidalDiseasesParseStats:
    pages_discovered: int = 0
    articles_fetched: int = 0
    articles_ok: int = 0
    errors: list[str] = field(default_factory=list)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
    return session


def _fetch(session: requests.Session, url: str, *, timeout: int = 35) -> str | None:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        logger.warning("vidal disease fetch failed %s: %s", url, exc)
        return None


def _should_skip_path(path: str) -> bool:
    low = path.lower()
    parts = low.strip("/").split("/")
    if len(parts) < 3:
        return True
    category, slug = parts[1], parts[2]
    if category in SKIP_CATEGORY:
        return True
    return any(p in slug for p in SKIP_SLUG_PARTS)


def discover_encyclopedia_paths(session: requests.Session) -> list[str]:
    """Collect /encyclopedia/<cat>/<slug> links from disease hub + category pages."""
    seen: set[str] = set()
    seed_urls = [
        DISEASE_INDEX,
        f"{VIDAL_BASE}/encyclopedia",
        # Some Vidal pages embed the full A–Я disease list under a sample slug.
        f"{VIDAL_BASE}/drugs/disease/amebiasis",
        f"{VIDAL_BASE}/drugs/disease/allergy",
    ]

    for url in seed_urls:
        html = _fetch(session, url)
        if not html:
            continue
        for path in ENCY_LINK_RE.findall(html):
            if _should_skip_path(path):
                continue
            seen.add(path)
        time.sleep(0.2)

    # Crawl category hubs discovered from article paths.
    categories = sorted({p.strip("/").split("/")[1] for p in seen if p.count("/") >= 2})
    for cat in categories:
        if cat in SKIP_CATEGORY:
            continue
        html = _fetch(session, f"{VIDAL_BASE}/encyclopedia/{cat}")
        if not html:
            continue
        for path in ENCY_LINK_RE.findall(html):
            if _should_skip_path(path):
                continue
            seen.add(path)
        time.sleep(0.25)

    return sorted(seen)


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|section)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _unescape_html(text: str) -> str:
    text = text or ""
    text = (
        text.replace("&nbsp;", " ")
        .replace("&ndash;", "–")
        .replace("&mdash;", "—")
        .replace("&laquo;", "«")
        .replace("&raquo;", "»")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("\\n", "\n")
        .replace("\\/", "/")
    )
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    return text


def _extract_jsonld_article_body(html: str) -> str:
    m = re.search(r'"articleBody"\s*:\s*"(.*?)"\s*[,}]', html or "", re.S)
    if not m:
        return ""
    return _unescape_html(m.group(1)).strip()


def _map_section_title(title: str) -> str | None:
    from apps.catalog.disease_sections import DISEASE_SECTION_DEFS

    title_l = (title or "").casefold().strip()
    if not title_l:
        return None
    for key, canon, aliases in DISEASE_SECTION_DEFS:
        if title_l == canon.casefold() or any(a in title_l for a in aliases):
            return key
    for key, _canon, aliases in DISEASE_SECTION_DEFS:
        if any(title_l.startswith(a) for a in aliases):
            return key
    return None


def parse_disease_article(html: str, *, path: str) -> dict[str, Any]:
    from apps.catalog.disease_sections import (
        DISEASE_SECTION_DEFS,
        build_disease_sections,
        parse_disease_labeled_blocks,
    )

    name = path.rstrip("/").split("/")[-1].replace("-", " ").strip().title()
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if h1:
        cleaned = re.sub(r"<[^>]+>", " ", h1.group(1))
        name = re.sub(r"\s+", " ", cleaned).strip() or name
        if "(" in name:
            left, _right = name.split("(", 1)
            if re.search(r"[А-Яа-яЁё]", left):
                name = left.strip()

    labeled: dict[str, str] = {}

    # 1) H2 sections (older Vidal layout, e.g. amebiasis).
    parts = re.split(r"<h2[^>]*>", html, flags=re.I)
    for part in parts[1:]:
        m = re.match(r"(.*?)</h2>(.*)", part, re.I | re.S)
        if not m:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
        body_html = re.split(r"(?i)<h2\b|class=\"footer|id=\"protec", m.group(2))[0]
        body = re.sub(r"(?i)#yad_article[\s\S]{0,400}", " ", _html_to_text(body_html))
        body = re.sub(r"\s+", " ", body).strip()
        mapped = _map_section_title(title)
        if mapped and len(body) >= 40:
            labeled[mapped] = body[:12000]

    # 2) JSON-LD articleBody (most encyclopedia pages — no <h2>).
    if len(labeled) < 2:
        article = _extract_jsonld_article_body(html)
        if article:
            # Drop leading image captions like "Бородавки // Источник: Unsplash"
            article = re.sub(r"(?m)^\s*.*?//\s*Источник:.*$", "", article)
            for key, title, _aliases in DISEASE_SECTION_DEFS:
                article = re.sub(
                    rf"(?<!\n)({re.escape(title)})",
                    r"\n\1\n",
                    article,
                    count=1,
                    flags=re.I,
                )
            from_blocks = parse_disease_labeled_blocks(article)
            for key, text in from_blocks.items():
                if key not in labeled or len(text) > len(labeled[key]):
                    labeled[key] = text[:12000]
            # If still almost empty — store whole article as overview.
            if not labeled and len(article) > 80:
                labeled["overview"] = re.sub(r"\s+", " ", article).strip()[:12000]

    # 3) Plain HTML text fallback.
    if len(labeled) < 2:
        plain = _html_to_text(html)
        from_blocks = parse_disease_labeled_blocks(plain)
        for key, text in from_blocks.items():
            if key not in labeled or len(text) > len(labeled[key]):
                labeled[key] = text[:12000]

    sections = build_disease_sections(description="", instructions="", stored=labeled)
    instructions = "\n\n".join(f"{row['title']}\n{row['text']}" for row in sections)[:30000]
    description = (
        labeled.get("overview")
        or labeled.get("symptoms")
        or labeled.get("causes")
        or ""
    )[:2000]

    return {
        "name": name[:255],
        "description": description,
        "instructions": instructions,
        "sections": labeled,
        "external_source": "vidal_encyclopedia",
        "external_id": path.strip("/"),
        "source_url": urljoin(VIDAL_BASE, path),
    }


def collect_vidal_diseases(
    *,
    delay_sec: float = 0.45,
    limit: int = 0,
    existing: dict[str, dict[str, Any]] | None = None,
    force: bool = False,
    on_article: Callable[[dict[str, Any], VidalDiseasesParseStats], None] | None = None,
) -> tuple[list[dict[str, Any]], VidalDiseasesParseStats]:
    session = _session()
    stats = VidalDiseasesParseStats()
    paths = discover_encyclopedia_paths(session)
    stats.pages_discovered = len(paths)
    if limit > 0:
        paths = paths[:limit]

    by_key = dict(existing or {})
    done_ids = {
        str(v.get("external_id") or "").strip("/")
        for v in by_key.values()
        if len(str(v.get("instructions") or "").strip()) >= 120
    }
    for path in paths:
        path_id = path.strip("/")
        if path_id in done_ids and not force:
            continue
        key = f"vidal:{path_id}"
        html = _fetch(session, urljoin(VIDAL_BASE, path))
        stats.articles_fetched += 1
        if not html:
            stats.errors.append(path)
            time.sleep(delay_sec)
            continue
        try:
            item = parse_disease_article(html, path=path)
        except Exception as exc:  # pragma: no cover
            stats.errors.append(f"{path}: {exc}")
            time.sleep(delay_sec)
            continue
        if not item.get("instructions") and not item.get("description"):
            stats.errors.append(f"{path}: empty")
            time.sleep(delay_sec)
            continue
        by_key[key] = item
        done_ids.add(path_id)
        stats.articles_ok += 1
        if on_article:
            on_article(item, stats)
        time.sleep(delay_sec)

    result = sorted(by_key.values(), key=lambda x: x.get("name", ""))
    return result, stats


def save_diseases_json(items: list[dict[str, Any]], path: Path, *, meta: dict | None = None) -> None:
    save_catalog_json(items, path, entity="disease", source="vidal_encyclopedia", meta=meta)


def load_diseases_json(path: Path) -> list[dict[str, Any]]:
    return load_catalog_json(path)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"completed": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
