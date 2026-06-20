"""Parser for drug analogs from vidal.ru (ТЗ §8.2.3)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

import requests

from apps.catalog.models import Drug
from apps.medic.models import DrugAnalog

logger = logging.getLogger(__name__)

VIDAL_BASE = "https://www.vidal.ru"
VIDAL_ANALOG_URL = "https://www.vidal.ru/analog"
SEARCH_URL = f"{VIDAL_BASE}/search"
USER_AGENT = "MedicAI-Importer/1.0 (+https://medic-ai.ru; data import per TZ)"


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self._capture = False
        self._buffer = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: v for k, v in attrs if v}
        if tag == "a" and "href" in attr_map:
            href = attr_map["href"]
            if "/drugs/" in href or "/analog" in href:
                self.links.append(href)

    def handle_data(self, data: str) -> None:
        self._buffer += data


@dataclass
class VidalParseResult:
    drugs_processed: int = 0
    analogs_created: int = 0
    analogs_updated: int = 0
    errors: list[str] = field(default_factory=list)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
    return session


def _fetch(session: requests.Session, url: str, *, timeout: int = 25) -> str | None:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        logger.warning("vidal fetch failed %s: %s", url, exc)
        return None


def _find_drug_page(session: requests.Session, drug_name: str) -> str | None:
    html = _fetch(session, f"{SEARCH_URL}?t=all&q={quote(drug_name)}")
    if not html:
        return None
    match = re.search(r'href="(/drugs/[^"]+)"', html)
    if match:
        return urljoin(VIDAL_BASE, match.group(1))
    return None


def _extract_analog_names(html: str) -> list[str]:
    names: list[str] = []
    for pattern in (
        r'class="[^"]*analog[^"]*"[^>]*>([^<]+)<',
        r'data-analog-name="([^"]+)"',
        r'/analog[^"]*"[^>]*>([^<]{2,120})<',
        r'>([A-ZА-ЯЁ][^<]{2,80})</a>\s*</(?:li|div|td)',
    ):
        for hit in re.findall(pattern, html, flags=re.IGNORECASE):
            cleaned = re.sub(r"\s+", " ", hit).strip(" .,")
            if len(cleaned) >= 3 and cleaned.lower() not in {"аналоги", "аналог", "vidal"}:
                names.append(cleaned)
    # dedupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
    return unique[:30]


def parse_analogs_for_drug(
    drug: Drug,
    *,
    session: requests.Session | None = None,
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    session = session or _session()
    errors: list[str] = []
    created = updated = 0

    drug_url = _find_drug_page(session, drug.name)
    if not drug_url:
        errors.append(f"«{drug.name}»: страница на vidal.ru не найдена")
        return created, updated, errors

    html = _fetch(session, drug_url)
    if not html:
        errors.append(f"«{drug.name}»: не удалось загрузить {drug_url}")
        return created, updated, errors

    analog_html = html
    analog_section = re.search(r"(аналог|substitut|generic)[\s\S]{0,8000}", html, flags=re.IGNORECASE)
    if analog_section:
        analog_html = analog_section.group(0)

    names = _extract_analog_names(analog_html)
    if not names:
        fallback = _fetch(session, f"{VIDAL_ANALOG_URL}?query={quote(drug.name)}")
        if fallback:
            names = _extract_analog_names(fallback)

    if not names:
        errors.append(f"«{drug.name}»: аналоги не найдены")
        return created, updated, errors

    for analog_name in names:
        if analog_name.lower() == drug.name.lower():
            continue
        existing = DrugAnalog.objects.filter(drug=drug, name__iexact=analog_name).first()
        if existing:
            if not existing.source_url and not dry_run:
                existing.source_url = drug_url
                existing.save(update_fields=["source_url"])
                updated += 1
            continue
        if dry_run:
            created += 1
            continue
        DrugAnalog.objects.create(
            drug=drug,
            name=analog_name,
            source_url=drug_url,
        )
        created += 1

    return created, updated, errors


def parse_vidal_analogs(
    *,
    drug_ids: list[int] | None = None,
    limit: int = 20,
    delay_sec: float = 1.0,
    dry_run: bool = False,
) -> VidalParseResult:
    result = VidalParseResult()
    qs = Drug.objects.all().order_by("name")
    if drug_ids:
        qs = qs.filter(pk__in=drug_ids)
    qs = qs[:limit]

    session = _session()
    for drug in qs:
        created, updated, errors = parse_analogs_for_drug(drug, session=session, dry_run=dry_run)
        result.drugs_processed += 1
        result.analogs_created += created
        result.analogs_updated += updated
        result.errors.extend(errors)
        if delay_sec > 0:
            time.sleep(delay_sec)
    return result
