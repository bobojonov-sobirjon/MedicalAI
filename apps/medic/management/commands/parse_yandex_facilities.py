"""
Yandex Maps → JSON (faqat parse, DB ga yozmaydi).

Terminal 1 (serverda, uzoq ishlaydi):
  python manage.py parse_yandex_facilities --all-cities --resume

Natija: data/exports/yandex_facilities.json
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.csv_import import iter_csv_rows, resolve_data_path
from apps.medic.importers.yandex_maps_parser import (
    collect_yandex_facilities,
    load_facilities_json,
    save_facilities_json,
    yandex_geocoder_api_key,
    yandex_search_api_key,
)
from apps.medic.importers.yandex_parse_state import (
    filter_pending_cities,
    load_parse_state,
    mark_city_completed,
    save_parse_state,
)

MEGA_CITIES = frozenset(
    {
        "москва",
        "санкт-петербург",
        "новосибирск",
        "екатеринбург",
        "казань",
        "нижний новгород",
        "красноярск",
        "челябинск",
        "самара",
        "уфа",
        "ростов-на-дону",
        "краснодар",
        "воронеж",
        "пермь",
        "волгоград",
    }
)


def _tile_spn_for_city(city: str, default: float) -> float:
    if city.strip().casefold() in MEGA_CITIES:
        return min(default, 0.06)
    return default


class Command(BaseCommand):
    help = "Parse Yandex Maps pharmacies/hospitals to JSON (Russia, resume supported)."

    def add_arguments(self, parser):
        parser.add_argument("--city", action="append", dest="cities", help="One city (repeatable)")
        parser.add_argument("--cities-file", default="cities_russia.csv", help="Cities CSV")
        parser.add_argument("--all-cities", action="store_true", help="All cities from CSV")
        parser.add_argument("--limit-cities", type=int, default=0)
        parser.add_argument("--kinds", default="pharmacy,hospital")
        parser.add_argument("--tile-spn", type=float, default=0.1)
        parser.add_argument("--max-pages", type=int, default=20)
        parser.add_argument("--delay", type=float, default=0.35)
        parser.add_argument("--fetch-org-photos", action="store_true", help="Extra API call per org for photos")
        parser.add_argument("--output", default="data/exports/yandex_facilities.json")
        parser.add_argument("--resume", action="store_true", help="Skip completed cities + merge JSON")
        parser.add_argument("--state-file", default="data/cache/yandex_parse_state.json")

    def handle(self, *args, **options):
        raise CommandError(
            "Yandex Maps parse o'chirildi (API kalit muammosi). "
            "OSM/Overpass ishlating:\n"
            "  python manage.py parse_osm_facilities --all-regions --resume\n"
            "  python manage.py import_osm_facilities --resume"
        )
