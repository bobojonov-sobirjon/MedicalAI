"""
Yandex Maps Geosearch API — aptekalar va bolnitsalar (ТЗ §5.8).

Kerak: YANDEX_MAPS_API_KEY (https://developer.tech.yandex.ru/)
API: https://search-maps.yandex.ru/v1/  va geocode-maps.yandex.ru
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SEARCH_URL = "https://search-maps.yandex.ru/v1/"
GEOCODE_URL = "https://geocode-maps.yandex.ru/1.x/"

PHARMACY_QUERY = "аптека"
HOSPITAL_QUERIES = ("больница", "поликлиника", "госпиталь", "медицинский центр")

PHARMACY_CLASSES = frozenset(
    {"drugstore", "pharmacy", "pharmacies", "apteka", "аптека", "pharmaceutical"}
)
HOSPITAL_CLASSES = frozenset(
    {
        "hospital",
        "clinic",
        "polyclinic",
        "medical",
        "health",
        "dentistry",
        "stomatology",
        "больница",
        "поликлиника",
        "госпиталь",
        "медицин",
        "клиника",
        "стоматолог",
    }
)

IMAGE_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+?(?:avatars\.mds\.yandex|yandex\.net|yastatic\.net)[^\s\"'<>]*",
    re.IGNORECASE,
)


@dataclass
class YandexParseStats:
    cities_processed: int = 0
    api_requests: int = 0
    facilities_total: int = 0
    pharmacies: int = 0
    hospitals: int = 0
    errors: list[str] = field(default_factory=list)
    auth_failed: bool = False


def yandex_search_api_key() -> str:
    return (getattr(settings, "YANDEX_MAPS_API_KEY", "") or "").strip()


def yandex_geocoder_api_key() -> str:
    return (
        getattr(settings, "YANDEX_GEOCODER_API_KEY", "")
        or getattr(settings, "YANDEX_MAPS_API_KEY", "")
        or ""
    ).strip()


def yandex_api_key() -> str:
    """Backward compat: search key required for parse."""
    return yandex_search_api_key() or yandex_geocoder_api_key()


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "MedicAI-YandexImporter/1.0",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": "application/json",
        }
    )
    return session


def _request_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    *,
    stats: YandexParseStats | None = None,
    timeout: int = 30,
) -> dict[str, Any] | None:
    if stats is not None:
        stats.api_requests += 1
    try:
        response = session.get(url, params=params, timeout=timeout)
        if response.status_code == 429:
            time.sleep(2.0)
            response = session.get(url, params=params, timeout=timeout)
            if stats is not None:
                stats.api_requests += 1
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        msg = f"Yandex API xato: {exc}"
        if getattr(exc, "response", None) is not None and exc.response is not None:
            body = exc.response.text[:200]
            if body:
                msg = f"{msg} | {body}"
            if exc.response.status_code == 403 and "api key" in body.lower():
                if stats is not None:
                    stats.auth_failed = True
        logger.warning(msg)
        if stats is not None:
            stats.errors.append(msg)
        return None


def _extract_images_from_obj(obj: Any) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_l = str(key).lower()
            if key_l in {"url", "href", "link", "src"} and isinstance(value, str) and value.startswith("http"):
                if any(host in value for host in ("yandex", "yastatic")):
                    found.append(value)
            elif key_l in {"photos", "photo", "images", "image", "gallery"}:
                found.extend(_extract_images_from_obj(value))
            else:
                found.extend(_extract_images_from_obj(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_extract_images_from_obj(item))
    elif isinstance(obj, str) and obj.startswith("http"):
        if IMAGE_URL_RE.search(obj):
            found.append(obj)
    # dedupe
    seen: set[str] = set()
    unique: list[str] = []
    for url in found:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _load_city_bbox_fallback() -> dict[str, dict]:
    path = Path(settings.BASE_DIR) / "data" / "cache" / "cities_bbox_fallback.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def geocode_city(
    session: requests.Session,
    city_name: str,
    *,
    api_key: str,
    stats: YandexParseStats | None = None,
    cache: dict[str, dict] | None = None,
) -> dict[str, Any] | None:
    if cache is not None and city_name in cache:
        return cache[city_name]

    params = {
        "apikey": api_key,
        "geocode": f"{city_name}, Россия",
        "format": "json",
        "results": 1,
        "lang": "ru_RU",
    }
    data = _request_json(session, GEOCODE_URL, params, stats=stats)
    if data:
        members = (
            data.get("response", {})
            .get("GeoObjectCollection", {})
            .get("featureMember", [])
        )
        if members:
            geo = members[0].get("GeoObject", {})
            pos = geo.get("Point", {}).get("pos", "")
            parts = pos.split()
            if len(parts) == 2:
                lon, lat = float(parts[0]), float(parts[1])
                envelope = geo.get("boundedBy", {}).get("Envelope", {})
                lower = envelope.get("lowerCorner", f"{lon} {lat}").split()
                upper = envelope.get("upperCorner", f"{lon} {lat}").split()
                bbox = {
                    "min_lon": float(lower[0]),
                    "min_lat": float(lower[1]),
                    "max_lon": float(upper[0]),
                    "max_lat": float(upper[1]),
                }
                result = {
                    "city_name": city_name,
                    "longitude": lon,
                    "latitude": lat,
                    "bbox": bbox,
                    "display_name": geo.get("name", city_name),
                    "source": "yandex_geocoder",
                }
                if cache is not None:
                    cache[city_name] = result
                return result

    fallback = _load_city_bbox_fallback().get(city_name)
    if fallback:
        result = {
            "city_name": city_name,
            "longitude": fallback["longitude"],
            "latitude": fallback["latitude"],
            "bbox": fallback["bbox"],
            "display_name": city_name,
            "source": "bbox_fallback",
        }
        if cache is not None:
            cache[city_name] = result
        if stats is not None:
            stats.errors.append(f"Geocoder API ishlamadi, fallback bbox: {city_name}")
        return result

    return None


def _grid_tiles(bbox: dict[str, float], *, tile_spn: float) -> list[tuple[float, float, float, float]]:
    """Return list of (center_lon, center_lat, spn_lon, spn_lat)."""
    min_lon, min_lat = bbox["min_lon"], bbox["min_lat"]
    max_lon, max_lat = bbox["max_lon"], bbox["max_lat"]
    width = max(max_lon - min_lon, tile_spn)
    height = max(max_lat - min_lat, tile_spn)

    tiles: list[tuple[float, float, float, float]] = []
    lon = min_lon + tile_spn / 2
    while lon <= max_lon + tile_spn / 2:
        lat = min_lat + tile_spn / 2
        while lat <= max_lat + tile_spn / 2:
            spn_lon = min(tile_spn, width)
            spn_lat = min(tile_spn, height)
            tiles.append((lon, lat, spn_lon, spn_lat))
            lat += tile_spn
        lon += tile_spn
    return tiles or [( (min_lon + max_lon) / 2, (min_lat + max_lat) / 2, width, height)]


def search_organizations(
    session: requests.Session,
    *,
    api_key: str,
    text: str,
    lon: float,
    lat: float,
    spn_lon: float,
    spn_lat: float,
    skip: int = 0,
    results: int = 50,
    stats: YandexParseStats | None = None,
) -> dict[str, Any] | None:
    params = {
        "apikey": api_key,
        "text": text,
        "type": "biz",
        "lang": "ru_RU",
        "ll": f"{lon},{lat}",
        "spn": f"{spn_lon},{spn_lat}",
        "rspn": 1,
        "results": results,
        "skip": skip,
    }
    return _request_json(session, SEARCH_URL, params, stats=stats)


def fetch_org_by_uri(
    session: requests.Session,
    *,
    api_key: str,
    uri: str,
    stats: YandexParseStats | None = None,
) -> dict[str, Any] | None:
    params = {"apikey": api_key, "uri": uri, "lang": "ru_RU"}
    return _request_json(session, SEARCH_URL, params, stats=stats)


def _classify_kind(categories: list[dict]) -> str | None:
    classes = " ".join(
        f"{c.get('class', '')} {c.get('name', '')}".lower() for c in categories
    )
    if any(token in classes for token in PHARMACY_CLASSES):
        return "pharmacy"
    if any(token in classes for token in HOSPITAL_CLASSES):
        return "hospital"
    # fallback by keywords in class string
    if "аптек" in classes or "drug" in classes:
        return "pharmacy"
    if "больниц" in classes or "клиник" in classes or "поликлин" in classes:
        return "hospital"
    return None


def _first_phone(phones: list[dict] | None) -> str:
    if not phones:
        return ""
    for item in phones:
        formatted = (item.get("formatted") or "").strip()
        if formatted:
            return formatted
    return ""


def parse_feature(
    feature: dict[str, Any],
    *,
    city_name: str,
    default_kind: str | None = None,
) -> dict[str, Any] | None:
    props = feature.get("properties") or {}
    company = props.get("CompanyMetaData") or {}
    if not company:
        return None

    external_id = str(company.get("id") or "").strip()
    if not external_id:
        uri = props.get("uri") or ""
        if "oid=" in uri:
            external_id = uri.split("oid=")[-1].split("&")[0]

    name = (company.get("name") or props.get("name") or "").strip()
    if not name:
        return None

    categories = company.get("Categories") or []
    kind = _classify_kind(categories) or default_kind
    if kind not in {"pharmacy", "hospital"}:
        return None

    address = company.get("address") or ""
    addr_obj = company.get("Address") or {}
    if not address and addr_obj:
        address = addr_obj.get("formatted") or ""

    hours = company.get("Hours") or {}
    hours_text = hours.get("text") or ""

    coords = feature.get("geometry", {}).get("coordinates") or []
    lon = lat = None
    if len(coords) >= 2:
        lon, lat = float(coords[0]), float(coords[1])

    images = _extract_images_from_obj(company)
    if not images:
        images = _extract_images_from_obj(feature)

    return {
        "kind": kind,
        "city_name": city_name,
        "name": name,
        "address": address,
        "phone": _first_phone(company.get("Phones")),
        "hours_text": hours_text,
        "latitude": lat,
        "longitude": lon,
        "external_source": "yandex",
        "external_id": external_id,
        "description": (props.get("description") or "").strip(),
        "image_url": images[0] if images else "",
        "images": images,
        "categories": categories,
        "yandex_url": company.get("url") or "",
        "yandex_uri": props.get("uri") or "",
    }


def _iter_city_searches(
    city_name: str,
    geo: dict[str, Any],
    *,
    kinds: set[str],
    tile_spn: float,
) -> Iterator[tuple[str, float, float, float, float]]:
    bbox = geo["bbox"]
    tiles = _grid_tiles(bbox, tile_spn=tile_spn)
    for lon, lat, spn_lon, spn_lat in tiles:
        if "pharmacy" in kinds:
            yield PHARMACY_QUERY, lon, lat, spn_lon, spn_lat
        if "hospital" in kinds:
            for q in HOSPITAL_QUERIES:
                yield q, lon, lat, spn_lon, spn_lat


def collect_yandex_facilities(
    cities: list[str],
    *,
    search_api_key: str | None = None,
    geocoder_api_key: str | None = None,
    kinds: set[str] | None = None,
    tile_spn: float = 0.12,
    max_pages_per_query: int = 20,
    delay_sec: float = 0.35,
    fetch_org_photos: bool = True,
    geocode_cache_path: Path | None = None,
    existing: dict[str, dict] | None = None,
    on_progress: Callable[[str, list[dict[str, Any]], YandexParseStats], None] | None = None,
) -> tuple[list[dict[str, Any]], YandexParseStats]:
    """
    Collect facilities for given Russian cities.
    Dedup key: yandex external_id.
    """
    search_key = search_api_key or yandex_search_api_key()
    geocode_key = geocoder_api_key or yandex_geocoder_api_key()
    if not search_key:
        raise ValueError("YANDEX_MAPS_API_KEY is not set in settings / .env")
    if not geocode_key:
        raise ValueError("YANDEX_GEOCODER_API_KEY is not set in settings / .env")

    kinds = kinds or {"pharmacy", "hospital"}
    stats = YandexParseStats()
    session = _session()
    facilities: dict[str, dict[str, Any]] = dict(existing or {})

    geocode_cache: dict[str, dict] = {}
    if geocode_cache_path and geocode_cache_path.exists():
        try:
            geocode_cache = json.loads(geocode_cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            geocode_cache = {}

    for city_name in cities:
        city_name = city_name.strip()
        if not city_name:
            continue

        geo = geocode_city(session, city_name, api_key=geocode_key, stats=stats, cache=geocode_cache)
        if not geo:
            stats.errors.append(f"Geocode topilmadi: {city_name}")
            continue

        stats.cities_processed += 1
        if geocode_cache_path:
            geocode_cache_path.parent.mkdir(parents=True, exist_ok=True)
            geocode_cache_path.write_text(
                json.dumps(geocode_cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        for query, lon, lat, spn_lon, spn_lat in _iter_city_searches(
            city_name, geo, kinds=kinds, tile_spn=tile_spn
        ):
            default_kind = "pharmacy" if query == PHARMACY_QUERY else "hospital"
            for page in range(max_pages_per_query):
                skip = page * 50
                data = search_organizations(
                    session,
                    api_key=search_key,
                    text=f"{query} {city_name}",
                    lon=lon,
                    lat=lat,
                    spn_lon=spn_lon,
                    spn_lat=spn_lat,
                    skip=skip,
                    stats=stats,
                )
                if delay_sec > 0:
                    time.sleep(delay_sec)

                if stats.auth_failed:
                    break

                if not data:
                    break

                features = data.get("features") or []
                if not features:
                    break

                for feature in features:
                    row = parse_feature(feature, city_name=city_name, default_kind=default_kind)
                    if not row or not row.get("external_id"):
                        continue
                    key = f"yandex:{row['external_id']}"
                    facilities[key] = row

                found = (
                    data.get("properties", {})
                    .get("ResponseMetaData", {})
                    .get("SearchResponse", {})
                    .get("found", 0)
                )
                if skip + 50 >= int(found) or len(features) < 50:
                    break

            if stats.auth_failed:
                break

        if on_progress:
            on_progress(city_name, list(facilities.values()), stats)

        if stats.auth_failed:
            stats.errors.append("API kalit rad etildi (403). Parse to'xtatildi.")
            break

    if fetch_org_photos and not stats.auth_failed:
        for key, row in list(facilities.items()):
            if row.get("images"):
                continue
            uri = row.get("yandex_uri") or ""
            if not uri:
                continue
            detail = fetch_org_by_uri(session, api_key=search_key, uri=uri, stats=stats)
            if delay_sec > 0:
                time.sleep(delay_sec)
            if not detail:
                continue
            for feature in detail.get("features") or []:
                extra_images = _extract_images_from_obj(feature)
                if extra_images:
                    row["images"] = extra_images
                    row["image_url"] = extra_images[0]
                    facilities[key] = row
                    break

    result_list = sorted(facilities.values(), key=lambda x: (x.get("city_name", ""), x.get("name", "")))
    stats.facilities_total = len(result_list)
    stats.pharmacies = sum(1 for x in result_list if x.get("kind") == "pharmacy")
    stats.hospitals = sum(1 for x in result_list if x.get("kind") == "hospital")
    return result_list, stats


def save_facilities_json(
    facilities: list[dict[str, Any]],
    path: Path,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    from .facilities_json import save_facilities_json as _save

    _save(facilities, path, source="yandex_maps", meta=meta)


def load_facilities_json(path: Path) -> list[dict[str, Any]]:
    from .facilities_json import load_facilities_json as _load

    return _load(path)
