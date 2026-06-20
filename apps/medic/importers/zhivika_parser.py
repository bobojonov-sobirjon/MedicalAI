"""Parser for drug prices from zhivika.ru (ТЗ §8.2.3)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import requests

from apps.catalog.models import Drug
from apps.medic.models import DrugAnalog

logger = logging.getLogger(__name__)

ZHIVIKA_SEARCH = "https://zhivika.ru/search"
USER_AGENT = "MedicAI-Importer/1.0 (+https://medic-ai.ru; data import per TZ)"


@dataclass
class ZhivikaParseResult:
    items_processed: int = 0
    prices_updated: int = 0
    errors: list[str] = field(default_factory=list)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
    return session


def _parse_price(text: str) -> Decimal | None:
    match = re.search(r"(\d[\d\s]*(?:[.,]\d{1,2})?)", text.replace("\xa0", " "))
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _fetch_price(session: requests.Session, query: str) -> tuple[Decimal | None, str]:
    url = f"{ZHIVIKA_SEARCH}?q={quote(query)}"
    try:
        response = session.get(url, timeout=25)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("zhivika fetch failed %s: %s", query, exc)
        return None, url

    html = response.text
    for pattern in (
        r'class="[^"]*price[^"]*"[^>]*>([^<]+)<',
        r'itemprop="price"[^>]*content="([^"]+)"',
        r'data-price="([^"]+)"',
        r'(\d[\d\s]{2,6}[.,]\d{2})\s*(?:₽|руб)',
    ):
        for hit in re.findall(pattern, html, flags=re.IGNORECASE):
            price = _parse_price(hit if isinstance(hit, str) else str(hit))
            if price and price > 0:
                return price, url
    return None, url


def parse_zhivika_prices(
    *,
    drug_ids: list[int] | None = None,
    analogs_only: bool = True,
    limit: int = 30,
    delay_sec: float = 1.0,
    dry_run: bool = False,
) -> ZhivikaParseResult:
    result = ZhivikaParseResult()
    session = _session()

    if analogs_only:
        analog_qs = DrugAnalog.objects.select_related("drug").order_by("drug__name", "name")
        if drug_ids:
            analog_qs = analog_qs.filter(drug_id__in=drug_ids)
        targets = list(analog_qs[:limit])
        for row in targets:
            result.items_processed += 1
            price, source_url = _fetch_price(session, row.name)
            if price is None:
                result.errors.append(f"«{row.name}»: цена не найдена на zhivika.ru")
            elif not dry_run:
                row.price = price
                if source_url:
                    row.source_url = source_url
                row.save(update_fields=["price", "source_url"])
                result.prices_updated += 1
            else:
                result.prices_updated += 1
            if delay_sec > 0:
                time.sleep(delay_sec)
        return result

    drug_qs = Drug.objects.all().order_by("name")
    if drug_ids:
        drug_qs = drug_qs.filter(pk__in=drug_ids)
    for drug in drug_qs[:limit]:
        result.items_processed += 1
        price, source_url = _fetch_price(session, drug.name)
        if price is None:
            result.errors.append(f"«{drug.name}»: цена не найдена")
        elif not dry_run:
            analog, _ = DrugAnalog.objects.get_or_create(
                drug=drug,
                name=drug.name,
                defaults={"source_url": source_url},
            )
            analog.price = price
            analog.source_url = source_url
            analog.save(update_fields=["price", "source_url"])
            result.prices_updated += 1
        else:
            result.prices_updated += 1
        if delay_sec > 0:
            time.sleep(delay_sec)
    return result
