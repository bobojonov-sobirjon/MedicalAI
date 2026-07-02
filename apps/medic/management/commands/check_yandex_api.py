"""Test Yandex API keys before long parse."""

from __future__ import annotations

import requests
from django.core.management.base import BaseCommand

from apps.medic.importers.yandex_maps_parser import yandex_geocoder_api_key, yandex_search_api_key


class Command(BaseCommand):
    help = "Check Yandex Search + Geocoder API keys (quick test)."

    def handle(self, *args, **options):
        search_key = yandex_search_api_key()
        geo_key = yandex_geocoder_api_key()
        if not search_key:
            self.stdout.write(self.style.ERROR("YANDEX_MAPS_API_KEY yo'q"))
            return
        if not geo_key:
            self.stdout.write(self.style.ERROR("YANDEX_GEOCODER_API_KEY yo'q"))
            return

        self.stdout.write("Search API test...")
        r1 = requests.get(
            "https://search-maps.yandex.ru/v1/",
            params={
                "apikey": search_key,
                "text": "аптека",
                "type": "biz",
                "lang": "ru_RU",
                "results": 3,
                "ll": "37.617635,55.755814",
                "spn": "0.2,0.2",
            },
            timeout=25,
        )
        if r1.ok:
            n = len(r1.json().get("features", []))
            self.stdout.write(self.style.SUCCESS(f"  OK: {n} ta natija (Поиск по организациям)"))
        else:
            self.stdout.write(self.style.ERROR(f"  FAIL {r1.status_code}: {r1.text[:180]}"))

        self.stdout.write("Geocoder API test...")
        r2 = requests.get(
            "https://geocode-maps.yandex.ru/1.x/",
            params={
                "apikey": geo_key,
                "geocode": "Москва, Россия",
                "format": "json",
                "results": 1,
            },
            timeout=25,
        )
        if r2.ok:
            self.stdout.write(self.style.SUCCESS("  OK (Геокодер)"))
        else:
            self.stdout.write(self.style.WARNING(f"  FAIL {r2.status_code}: {r2.text[:180]}"))
            self.stdout.write("  (5 ta shahar uchun bbox fallback ishlaydi)")
