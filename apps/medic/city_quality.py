from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from apps.core.csv_import import iter_csv_rows, resolve_data_path
from apps.medic.importers.city_normalize import clean_city_label, is_blocked_city_name
from apps.medic.models import City, MedicalFacility

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_ONLY_RE = re.compile(r"^[A-Za-z\s\-'.]+$")

KNOWN_LATIN_CITY_ALIASES = {
    "moskva": "Москва",
    "saint petersburg": "Санкт-Петербург",
    "st petersburg": "Санкт-Петербург",
}


@lru_cache(maxsize=1)
def curated_major_city_names() -> frozenset[str]:
    """Major Russian cities from bundled CSV (picker whitelist)."""
    base = Path(settings.BASE_DIR)
    path = resolve_data_path("cities_russia.csv", base=base)
    names: set[str] = set()
    if path.exists():
        for row in iter_csv_rows(path):
            name = clean_city_label(row.get("name") or row.get("city") or "")
            if name:
                names.add(name)
    return frozenset(names)


def is_curated_major_city(name: str) -> bool:
    return clean_city_label(name) in curated_major_city_names()


def has_cyrillic(text: str) -> bool:
    return bool(CYRILLIC_RE.search(text or ""))


def is_latin_only_city_name(name: str) -> bool:
    label = clean_city_label(name)
    if not label:
        return False
    if has_cyrillic(label):
        return False
    return bool(LATIN_ONLY_RE.match(label))


def latin_city_to_cyrillic(name: str) -> str | None:
    key = clean_city_label(name).lower()
    return KNOWN_LATIN_CITY_ALIASES.get(key)


def is_junk_city_name(name: str) -> bool:
    label = clean_city_label(name)
    if not label:
        return True
    if is_blocked_city_name(label):
        return True
    if is_latin_only_city_name(label):
        return True
    if label not in curated_major_city_names() and len(label) > 24:
        return True
    return False


def is_osm_junk_city(city: City) -> bool:
    """OSM-imported settlement, not a major city for the picker."""
    if is_curated_major_city(city.name):
        return False
    if city.sort_order and city.sort_order > 0:
        return False
    if is_junk_city_name(city.name):
        return True
    # sort_order=0 and not in curated list -> junk from OSM auto-create
    return True


def iter_junk_cities():
    for city in City.objects.all().only("id", "name", "geo_level", "sort_order"):
        if is_osm_junk_city(city):
            yield city


def city_has_facilities(city_id: int) -> bool:
    return MedicalFacility.objects.filter(city_id=city_id).exists()
