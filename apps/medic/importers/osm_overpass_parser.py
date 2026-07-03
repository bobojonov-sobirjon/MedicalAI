"""
OpenStreetMap Overpass API — aptekalar va shifoxonalar (Rossiya, viloyatlar bo'yicha).

API: https://overpass-api.de/api/interpreter (HTTPS + User-Agent majburiy)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests

from .facilities_json import load_facilities_json, save_facilities_json

from .facility_image_resolver import OSM_IMAGE_KEYS
from .facility_name_normalize import NAME_TAG_KEYS

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "MedicAI-OSMParser/1.0 (https://medic-ai.ru; facility import)"

PHARMACY_AMENITIES = frozenset({"pharmacy", "chemist"})
HOSPITAL_AMENITIES = frozenset({"hospital", "clinic", "doctors"})
PHARMACY_HEALTHCARE = frozenset({"pharmacy", "chemist"})
HOSPITAL_HEALTHCARE = frozenset({"hospital", "clinic", "centre", "doctor"})

WIKIMEDIA_RE = re.compile(r"^File:(.+)$", re.IGNORECASE)


@dataclass
class OsmParseStats:
    regions_processed: int = 0
    api_requests: int = 0
    facilities_total: int = 0
    pharmacies: int = 0
    hospitals: int = 0
    errors: list[str] = field(default_factory=list)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def load_regions_catalog(path: Path) -> dict[str, dict[str, str]]:
    """Index regions CSV by lowercase name and ISO3166-2."""
    from apps.core.csv_import import iter_csv_rows

    by_key: dict[str, dict[str, str]] = {}
    if not path.exists():
        return by_key
    for row in iter_csv_rows(path):
        name = (row.get("name") or row.get("region") or "").strip()
        iso = (row.get("iso3166_2") or row.get("iso") or "").strip().upper()
        overpass_name = (row.get("overpass_name") or "").strip()
        entry = {"name": name, "iso3166_2": iso, "overpass_name": overpass_name}
        if iso:
            by_key[iso.casefold()] = entry
        if name:
            by_key[name.casefold()] = entry
        if overpass_name:
            by_key[overpass_name.casefold()] = entry
    return by_key


def resolve_region_row(raw: str | dict[str, str], catalog: dict[str, dict[str, str]]) -> dict[str, str]:
    if isinstance(raw, dict):
        name = (raw.get("name") or raw.get("region") or "").strip()
        iso = (raw.get("iso3166_2") or raw.get("iso") or "").strip().upper()
        overpass_name = (raw.get("overpass_name") or "").strip()
        if iso:
            return {"name": name or iso, "iso3166_2": iso, "overpass_name": overpass_name}
        if name:
            found = catalog.get(name.casefold())
            if found:
                return found
        return {"name": name, "iso3166_2": iso, "overpass_name": overpass_name}

    key = raw.strip()
    if not key:
        return {"name": "", "iso3166_2": ""}
    if key.upper().startswith("RU-"):
        found = catalog.get(key.casefold())
        return found or {"name": key, "iso3166_2": key.upper()}
    found = catalog.get(key.casefold())
    return found or {"name": key, "iso3166_2": ""}


def _build_region_query(*, iso3166_2: str = "", region_name: str = "", overpass_name: str = "", timeout: int = 180) -> str:
    if iso3166_2:
        area_selector = f'area["ISO3166-2"="{iso3166_2}"]'
    else:
        name = overpass_name or region_name
        if not name:
            raise ValueError("region needs iso3166_2 or name")
        escaped = name.replace('"', '\\"')
        area_selector = f'area["name"="{escaped}"]["admin_level"="4"]'

    return f"""
[out:json][timeout:{timeout}];
{area_selector}->.searchArea;
(
  node["amenity"~"^(pharmacy|chemist|hospital|clinic|doctors)$"](area.searchArea);
  way["amenity"~"^(pharmacy|chemist|hospital|clinic|doctors)$"](area.searchArea);
  relation["amenity"~"^(pharmacy|chemist|hospital|clinic|doctors)$"](area.searchArea);
  node["healthcare"~"^(pharmacy|chemist|hospital|clinic|centre|doctor)$"](area.searchArea);
  way["healthcare"~"^(pharmacy|chemist|hospital|clinic|centre|doctor)$"](area.searchArea);
  relation["healthcare"~"^(pharmacy|chemist|hospital|clinic|centre|doctor)$"](area.searchArea);
);
out center tags;
"""


def _request_overpass(
    session: requests.Session,
    query: str,
    *,
    stats: OsmParseStats | None = None,
    timeout: int = 200,
    retries: int = 2,
) -> dict[str, Any] | None:
    if stats is not None:
        stats.api_requests += 1

    for attempt in range(retries + 1):
        try:
            response = session.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=timeout,
            )
            if response.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning("Overpass 429, %ss kutamiz", wait)
                time.sleep(wait)
                if stats is not None:
                    stats.api_requests += 1
                continue
            if response.status_code == 504 and attempt < retries:
                time.sleep(10 * (attempt + 1))
                if stats is not None:
                    stats.api_requests += 1
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            if attempt < retries:
                time.sleep(8 * (attempt + 1))
                if stats is not None:
                    stats.api_requests += 1
                continue
            msg = f"Overpass xato: {exc}"
            logger.error(msg)
            if stats is not None:
                stats.errors.append(msg)
            return None
    return None


def _normalize_kind(tags: dict[str, str]) -> str | None:
    amenity = (tags.get("amenity") or "").strip().lower()
    healthcare = (tags.get("healthcare") or "").strip().lower()

    if amenity in PHARMACY_AMENITIES or healthcare in PHARMACY_HEALTHCARE:
        return "pharmacy"
    if amenity in HOSPITAL_AMENITIES or healthcare in HOSPITAL_HEALTHCARE:
        return "hospital"
    return None


def _build_address(tags: dict[str, str]) -> str:
    parts: list[str] = []
    street = tags.get("addr:street") or tags.get("addr:place") or ""
    house = tags.get("addr:housenumber") or ""
    if street and house:
        parts.append(f"{street}, {house}")
    elif street:
        parts.append(street)
    elif tags.get("addr:full"):
        parts.append(tags["addr:full"])

    city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or ""
    if city and parts:
        return f"{parts[0]}, {city}"
    if city:
        return city
    return ", ".join(parts)[:512]


def _city_name(tags: dict[str, str], region_fallback: str) -> str:
    from .city_normalize import resolve_city_name_from_osm_tags

    return resolve_city_name_from_osm_tags(tags, region_fallback=region_fallback)


def _pick_name(tags: dict[str, str]) -> str:
    from .facility_name_normalize import pick_facility_name_from_osm_tags

    return pick_facility_name_from_osm_tags(tags)


def _pick_phone(tags: dict[str, str]) -> str:
    for key in ("phone", "contact:phone", "contact:mobile"):
        value = (tags.get(key) or "").strip()
        if value:
            return value[:64]
    return ""


def _pick_image_url(tags: dict[str, str]) -> str:
    image = (tags.get("image") or tags.get("image:url") or tags.get("contact:image") or "").strip()
    if image.startswith("http"):
        return image

    commons = (tags.get("wikimedia_commons") or "").strip()
    if commons:
        match = WIKIMEDIA_RE.match(commons)
        if match:
            filename = match.group(1).replace(" ", "_")
            return f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"

    return ""


def _element_coords(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    lat = center.get("lat")
    lon = center.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None, None


def _element_to_facility(
    element: dict[str, Any],
    *,
    region_name: str,
    kinds: set[str],
) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    kind = _normalize_kind(tags)
    if kind is None or kind not in kinds:
        return None

    lat, lon = _element_coords(element)
    if lat is None or lon is None:
        return None

    name = _pick_name(tags)
    if not name:
        from .facility_name_normalize import build_fallback_facility_name, cleanup_facility_display_name

        kind_str = "pharmacy" if kind == "pharmacy" else "hospital"
        city_name = _city_name(tags, region_name)
        name = cleanup_facility_display_name(
            build_fallback_facility_name(
                kind=kind_str,
                city_name=city_name,
                address=_build_address(tags),
                latitude=lat,
                longitude=lon,
            )
        )
    if name:
        from .facility_name_normalize import cleanup_facility_display_name

        name = cleanup_facility_display_name(name)
    if not name:
        return None

    osm_type = element.get("type", "node")
    osm_id = element.get("id")
    if not osm_id:
        return None

    prefix = {"node": "n", "way": "w", "relation": "r"}.get(osm_type, "x")
    external_id = f"{prefix}{osm_id}"

    city_name = _city_name(tags, region_name)
    if not city_name:
        return None

    image_url = _pick_image_url(tags)
    wikidata_id = (tags.get("wikidata") or "").strip()
    brand_wikidata_id = (tags.get("brand:wikidata") or "").strip()
    image_tags = {
        key: value
        for key, value in tags.items()
        if key in OSM_IMAGE_KEYS
        or key == "wikimedia_commons"
        or key.startswith("image")
    }
    name_tags = {
        key: value
        for key, value in tags.items()
        if key in NAME_TAG_KEYS and (value or "").strip()
    }

    row: dict[str, Any] = {
        "kind": kind,
        "name": name[:255],
        "city_name": city_name[:128],
        "address": _build_address(tags),
        "phone": _pick_phone(tags),
        "hours_text": (tags.get("opening_hours") or "")[:255],
        "description": (tags.get("description") or tags.get("healthcare:speciality") or "")[:2000],
        "latitude": lat,
        "longitude": lon,
        "external_source": "osm",
        "external_id": external_id,
        "region_name": region_name,
        "osm_type": osm_type,
        "osm_id": osm_id,
    }
    if image_tags:
        row["osm_tags"] = image_tags
    if name_tags:
        row["osm_name_tags"] = name_tags
    if wikidata_id:
        row["wikidata_id"] = wikidata_id
    if brand_wikidata_id:
        row["brand_wikidata_id"] = brand_wikidata_id
    if image_url:
        row["image_url"] = image_url
        row["images"] = [image_url]
    return row


def fetch_region_facilities(
    region: dict[str, str],
    *,
    kinds: set[str] | None = None,
    session: requests.Session | None = None,
    stats: OsmParseStats | None = None,
    timeout: int = 180,
) -> list[dict[str, Any]]:
    kinds = kinds or {"pharmacy", "hospital"}
    region_name = (region.get("name") or region.get("region") or "").strip()
    iso3166_2 = (region.get("iso3166_2") or region.get("iso") or "").strip().upper()
    overpass_name = (region.get("overpass_name") or "").strip()
    if not region_name and not iso3166_2:
        return []

    session = session or _session()
    query = _build_region_query(
        iso3166_2=iso3166_2,
        region_name=region_name,
        overpass_name=overpass_name,
        timeout=timeout,
    )
    payload = _request_overpass(session, query, stats=stats, timeout=timeout + 30)
    if not payload:
        return []

    facilities: list[dict[str, Any]] = []
    fallback_region = region_name or iso3166_2
    for element in payload.get("elements") or []:
        row = _element_to_facility(element, region_name=fallback_region, kinds=kinds)
        if row:
            facilities.append(row)
    return facilities


def collect_osm_facilities(
    regions: list[dict[str, str]],
    *,
    kinds: set[str] | None = None,
    delay_sec: float = 8.0,
    existing: dict[str, dict[str, Any]] | None = None,
    on_region_done: Callable[[str, list[dict[str, Any]], OsmParseStats], None] | None = None,
) -> tuple[list[dict[str, Any]], OsmParseStats]:
    kinds = kinds or {"pharmacy", "hospital"}
    facilities_map = dict(existing or {})
    stats = OsmParseStats()
    session = _session()

    for region in regions:
        region_name = (region.get("name") or region.get("region") or region.get("iso3166_2") or "?").strip()
        rows = fetch_region_facilities(
            region,
            kinds=kinds,
            session=session,
            stats=stats,
        )
        for row in rows:
            eid = str(row.get("external_id") or "")
            if eid:
                facilities_map[f"osm:{eid}"] = row

        stats.regions_processed += 1
        result_list = sorted(facilities_map.values(), key=lambda x: (x.get("city_name", ""), x.get("name", "")))
        stats.facilities_total = len(result_list)
        stats.pharmacies = sum(1 for x in result_list if x.get("kind") == "pharmacy")
        stats.hospitals = sum(1 for x in result_list if x.get("kind") == "hospital")

        if on_region_done:
            on_region_done(region_name, result_list, stats)

        if delay_sec > 0:
            time.sleep(delay_sec)

    result = sorted(facilities_map.values(), key=lambda x: (x.get("city_name", ""), x.get("name", "")))
    return result, stats


def merge_facilities_from_file(path: Path) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return merged
    for row in load_facilities_json(path):
        source = (row.get("external_source") or "osm").strip()
        eid = str(row.get("external_id") or "")
        if eid:
            merged[f"{source}:{eid}"] = row
    return merged


def save_osm_facilities_json(
    facilities: list[dict[str, Any]],
    path: Path,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    save_facilities_json(facilities, path, source="osm", meta=meta)
