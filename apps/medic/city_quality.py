from __future__ import annotations

import re

from apps.medic.importers.city_normalize import clean_city_label, is_blocked_city_name
from apps.medic.models import City, MedicalFacility

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_ONLY_RE = re.compile(r"^[A-Za-z\s\-'.]+$")

KNOWN_LATIN_CITY_ALIASES = {
    "moskva": "Москва",
    "saint petersburg": "Санкт-Петербург",
    "st petersburg": "Санкт-Петербург",
}


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
    return False


def iter_junk_cities():
    for city in City.objects.all().only("id", "name", "geo_level"):
        if is_junk_city_name(city.name):
            yield city


def city_has_facilities(city_id: int) -> bool:
    return MedicalFacility.objects.filter(city_id=city_id).exists()
