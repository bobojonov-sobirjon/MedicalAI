"""Fill missing facility address/phone/hours.

Providers:
  • nominatim (FREE, no key) — только адрес по координатам (OSM Nominatim);
  • yandex (нужен платный ключ) — адрес + телефон + часы работы.
Существующие значения никогда не перезаписываются.
"""

from __future__ import annotations

import json
import math
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.medic.importers.yandex_maps_parser import (
    GEOCODE_URL,
    _request_json,
    _session,
    parse_feature,
    search_organizations,
    yandex_geocoder_api_key,
    yandex_search_api_key,
)
from apps.medic.models import MedicalFacility

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_UA = "MedicAI-FacilityEnrich/1.0 (+https://medic-ai.ru)"


_NON_WORD_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)
_GENERIC_RE = re.compile(
    r"^(?:аптека|больница|поликлиника|клиника|медицинский центр)\s+",
    re.IGNORECASE,
)


def _normal_name(value: str) -> str:
    value = _GENERIC_RE.sub("", (value or "").strip().casefold())
    return " ".join(_NON_WORD_RE.sub(" ", value).split())


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _name_score(left: str, right: str) -> float:
    a, b = _normal_name(left), _normal_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.88
    return SequenceMatcher(None, a, b).ratio()


def _reverse_address_nominatim(session, *, lat: float, lon: float) -> str:
    """Бесплатный reverse-geocode через OSM Nominatim (лимит ~1 запрос/сек)."""
    try:
        response = session.get(
            NOMINATIM_URL,
            params={
                "format": "jsonv2",
                "lat": f"{lat}",
                "lon": f"{lon}",
                "zoom": 18,
                "addressdetails": 1,
                "accept-language": "ru",
            },
            headers={"User-Agent": NOMINATIM_UA},
            timeout=30,
        )
        if response.status_code == 429:
            time.sleep(2.0)
            return ""
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return ""

    addr = data.get("address") or {}
    road = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or ""
    house = addr.get("house_number") or ""
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or ""
    )
    parts: list[str] = []
    if road and house:
        parts.append(f"{road}, {house}")
    elif road:
        parts.append(road)
    if city and city not in parts:
        parts.append(city)
    if parts:
        return ", ".join(parts)[:512]
    return str(data.get("display_name") or "").strip()[:512]


def _reverse_address(session, *, api_key: str, lat: float, lon: float) -> str:
    data = _request_json(
        session,
        GEOCODE_URL,
        {
            "apikey": api_key,
            "geocode": f"{lon},{lat}",
            "format": "json",
            "results": 1,
            "kind": "house",
            "lang": "ru_RU",
        },
    )
    members = (
        (data or {})
        .get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not members:
        return ""
    geo = members[0].get("GeoObject") or {}
    meta = geo.get("metaDataProperty", {}).get("GeocoderMetaData", {})
    address = meta.get("Address", {}).get("formatted") or meta.get("text") or ""
    return str(address).strip()[:512]


def _best_place(session, facility: MedicalFacility, *, api_key: str) -> dict | None:
    lat, lon = float(facility.latitude), float(facility.longitude)
    data = search_organizations(
        session,
        api_key=api_key,
        text=facility.name,
        lon=lon,
        lat=lat,
        spn_lon=0.01,
        spn_lat=0.01,
        results=10,
    )
    best: tuple[float, dict] | None = None
    for feature in (data or {}).get("features", []):
        row = parse_feature(
            feature,
            city_name=facility.city.name,
            default_kind=facility.kind,
        )
        if not row or row.get("kind") != facility.kind:
            continue
        cand_lat, cand_lon = row.get("latitude"), row.get("longitude")
        if cand_lat is None or cand_lon is None:
            continue
        distance = _distance_m(lat, lon, float(cand_lat), float(cand_lon))
        similarity = _name_score(facility.name, str(row.get("name") or ""))
        # Do not attach another organization's contacts: both proximity and name must match.
        if distance > 350 or similarity < 0.58:
            continue
        score = similarity - min(distance, 350) / 1400
        if best is None or score > best[0]:
            best = (score, row)
    return best[1] if best else None


class Command(BaseCommand):
    help = (
        "Fill EMPTY address/phone/hours from Yandex. "
        "Validated by coordinates/name; existing values are never overwritten."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Save changes (default: dry-run).")
        parser.add_argument(
            "--provider",
            choices=("nominatim", "yandex"),
            default="nominatim",
            help="nominatim=БЕСПЛАТНО, только адрес. yandex=адрес+телефон+часы (нужен платный ключ).",
        )
        parser.add_argument("--city", default="", help="Only this city name.")
        parser.add_argument("--kind", choices=("pharmacy", "hospital"), default="")
        parser.add_argument("--source", default="osm", help="DB external_source (default: osm).")
        parser.add_argument("--only", choices=("all", "address", "contacts"), default="all")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--delay", type=float, default=0.0, help="Задержка, сек (nominatim: минимум 1.0).")
        parser.add_argument(
            "--state-file",
            default="data/cache/facility_enrichment_state.json",
        )
        parser.add_argument("--resume", action="store_true")

    def handle(self, *args, **options):
        provider = options["provider"]
        only = options["only"]
        need_address = only in {"all", "address"}
        need_contacts = only in {"all", "contacts"}

        geocoder_key = ""
        search_key = ""
        if provider == "yandex":
            geocoder_key = yandex_geocoder_api_key() if need_address else ""
            search_key = yandex_search_api_key() if need_contacts else ""
            if need_address and not geocoder_key:
                raise CommandError("YANDEX_GEOCODER_API_KEY (yoki YANDEX_MAPS_API_KEY) sozlanmagan.")
            if need_contacts and not search_key:
                raise CommandError("YANDEX_MAPS_API_KEY sozlanmagan (telefon/rejim uchun Geosearch kerak).")
        else:
            # Nominatim — бесплатно, но только адрес.
            if need_contacts and only == "contacts":
                raise CommandError(
                    "provider=nominatim телефон/часы не умеет. "
                    "Используйте --only address, либо --provider yandex с платным ключом."
                )
            need_contacts = False
            if options["delay"] < 1.0:
                options["delay"] = 1.1  # соблюдаем usage policy Nominatim (<=1 req/s)
            self.stdout.write(
                self.style.WARNING(
                    "provider=nominatim: заполняем ТОЛЬКО адрес (бесплатно). "
                    "Телефон/часы требуют платного Yandex-ключа."
                )
            )

        qs = MedicalFacility.objects.select_related("city").filter(
            latitude__isnull=False,
            longitude__isnull=False,
        )
        source = (options["source"] or "").strip()
        if source:
            qs = qs.filter(external_source=source)
        if options["city"]:
            qs = qs.filter(city__name__iexact=options["city"].strip())
        if options["kind"]:
            qs = qs.filter(kind=options["kind"])
        missing = Q()
        if need_address:
            missing |= Q(address="")
        if need_contacts:
            missing |= Q(phone="") | Q(hours_text="")
        qs = qs.filter(missing).order_by("id")

        state_path = Path(settings.BASE_DIR) / options["state_file"]
        done = self._load_state(state_path) if options["resume"] else set()
        if done:
            qs = qs.exclude(id__in=done)
        if options["offset"] > 0:
            qs = qs[options["offset"] :]
        if options["limit"] > 0:
            qs = qs[: options["limit"]]

        session = _session()
        processed = changed = addresses = phones = hours = matched = 0
        for facility in qs.iterator(chunk_size=100):
            processed += 1
            update_fields: list[str] = []
            place = None

            if need_contacts and (not facility.phone or not facility.hours_text):
                place = _best_place(session, facility, api_key=search_key)
                if place:
                    matched += 1
                    if not facility.phone and place.get("phone"):
                        facility.phone = str(place["phone"])[:64]
                        update_fields.append("phone")
                        phones += 1
                    if not facility.hours_text and place.get("hours_text"):
                        facility.hours_text = str(place["hours_text"])[:255]
                        update_fields.append("hours_text")
                        hours += 1

            if need_address and not facility.address:
                address = str((place or {}).get("address") or "").strip()
                if not address:
                    if provider == "nominatim":
                        address = _reverse_address_nominatim(
                            session,
                            lat=float(facility.latitude),
                            lon=float(facility.longitude),
                        )
                    else:
                        address = _reverse_address(
                            session,
                            api_key=geocoder_key,
                            lat=float(facility.latitude),
                            lon=float(facility.longitude),
                        )
                if address:
                    facility.address = address[:512]
                    update_fields.append("address")
                    addresses += 1

            if update_fields:
                changed += 1
                if options["apply"]:
                    facility.save(update_fields=[*dict.fromkeys(update_fields), "updated_at"])
            if options["apply"] and options["resume"]:
                done.add(facility.id)
                if processed % 25 == 0:
                    self._save_state(state_path, done)
            if processed % 25 == 0:
                self.stdout.write(
                    f"processed={processed} changed={changed} address=+{addresses} "
                    f"phone=+{phones} hours=+{hours} place_match={matched}"
                )
            if options["delay"] > 0:
                time.sleep(options["delay"])

        if options["apply"] and options["resume"]:
            self._save_state(state_path, done)
        prefix = "" if options["apply"] else "[DRY-RUN] "
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}TUGADI: processed={processed}, changed={changed}, "
                f"address=+{addresses}, phone=+{phones}, hours=+{hours}, place_match={matched}"
            )
        )
        if not options["apply"]:
            self.stdout.write("Saqlash uchun shu komandani --apply bilan qayta ishga tushiring.")

    @staticmethod
    def _load_state(path: Path) -> set[int]:
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {int(value) for value in data.get("processed_ids", [])}
        except (ValueError, TypeError, json.JSONDecodeError):
            return set()

    @staticmethod
    def _save_state(path: Path, done: set[int]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"processed_ids": sorted(done), "count": len(done)}, indent=2),
            encoding="utf-8",
        )
