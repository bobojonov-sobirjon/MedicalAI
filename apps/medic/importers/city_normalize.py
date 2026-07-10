"""Normalize and validate Russian city/region names for the City model."""

from __future__ import annotations

import re

# OSM tags allowed as "city" in our catalog (viloyat/shahar/tuman only).
CITY_TAG_PRIORITY = (
    "addr:city",
    "addr:town",
    "addr:district",
)

# Never treat these as City.name (mahalla, ko'cha, mikrorayon, ...).
BLOCKED_TAG_KEYS = frozenset(
    {
        "addr:suburb",
        "addr:village",
        "addr:hamlet",
        "addr:neighbourhood",
        "addr:quarter",
        "addr:place",
        "addr:street",
        "addr:housenumber",
        "addr:postcode",
    }
)

INVALID_NAME_RE = re.compile(
    r"|".join(
        [
            r"\d+-й\s+микрорайон",
            r"\d+-й\s+квартал",
            r"\bмикрорайон\b",
            r"\bквартал\b",
            r"\bмахалл",
            r"\bпос[её]лок\b",
            r"\bпос\.\b",
            r"\bсело\b",
            r"\bдеревн",
            r"\bстаниц",
            r"\bхутор\b",
            r"\bаул\b",
            r"^(верхн|нижн|средн|верхне|нижне|средне|новое|старое)\b",
            r"\bул\.?\b",
            r"\bулиц",
            r"\bпроспект\b",
            r"\bпр\.?\b",
            r"\bпереулок\b",
            r"\bпер\.?\b",
            r"\bшоссе\b",
            r"\bнабережн",
            r"\bпроезд\b",
            r"\bтупик\b",
            r"\bлиния\b",
            r"^\d+\s*[-–]?\s*(й|я|ый|ая|ое)\b",
        ]
    ),
    re.IGNORECASE,
)

REGION_SUFFIX_RE = re.compile(
    r"(область|край|республика|округ|АО|автономн)",
    re.IGNORECASE,
)


def clean_city_label(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())[:128]


def is_blocked_city_name(name: str) -> bool:
    label = clean_city_label(name)
    if not label or len(label) < 2:
        return True
    if INVALID_NAME_RE.search(label):
        return True
    if label[0].isdigit() and not REGION_SUFFIX_RE.search(label):
        # "12-й квартал", "2 с Поныри" va hokazo
        if re.match(r"^\d", label):
            return True
    return False


def infer_geo_level(name: str) -> str:
    from apps.medic.models import City

    label = clean_city_label(name)
    if REGION_SUFFIX_RE.search(label):
        return City.GeoLevel.REGION
    if re.search(r"\bрайон\b", label, re.IGNORECASE):
        return City.GeoLevel.DISTRICT
    return City.GeoLevel.CITY


def resolve_city_name_from_osm_tags(tags: dict[str, str], *, region_fallback: str) -> str:
    """Pick viloyat / shahar / tuman from OSM; ignore mahalla and streets."""
    for key in CITY_TAG_PRIORITY:
        value = clean_city_label(tags.get(key) or "")
        if value and not is_blocked_city_name(value):
            return value

    fallback = clean_city_label(region_fallback)
    if fallback and not is_blocked_city_name(fallback):
        return fallback
    return ""


def pick_city_name_for_facility_row(row: dict, *, region_fallback: str = "") -> str:
    osm_tags = row.get("osm_tags") or {}
    if isinstance(osm_tags, dict) and osm_tags:
        name = resolve_city_name_from_osm_tags(osm_tags, region_fallback=region_fallback)
        if name:
            return name

    for key in ("city_name", "city"):
        value = clean_city_label(str(row.get(key) or ""))
        if value and not is_blocked_city_name(value):
            return value

    region = clean_city_label(str(row.get("region_name") or region_fallback or ""))
    if region and not is_blocked_city_name(region):
        return region
    return ""
