"""Promote settlement cities from facility addresses (e.g. Янаул under Республика Башкортостан)."""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.medic.importers.city_normalize import (
    REGION_SUFFIX_RE,
    clean_city_label,
    is_blocked_city_name,
)
from apps.medic.city_quality import is_latin_only_city_name
from apps.medic.models import City, MedicalFacility


_HOUSE_RE = re.compile(r"^\d+([а-яА-Яa-zA-Z/\-]*)?$")
_STREET_HINT_RE = re.compile(
    r"(улиц|ул\.|проспект|пр\.|переулок|пер\.|шоссе|набережн|проезд|бульвар)",
    re.IGNORECASE,
)


def settlement_from_address(address: str) -> str | None:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    if not parts:
        return None
    for part in reversed(parts):
        label = clean_city_label(part)
        if not label or len(label) < 2 or len(label) > 48:
            continue
        if _HOUSE_RE.match(label):
            continue
        if _STREET_HINT_RE.search(label):
            continue
        if REGION_SUFFIX_RE.search(label):
            continue
        if is_blocked_city_name(label) or is_latin_only_city_name(label):
            continue
        return label
    return None


def is_region_bucket_city(city: City) -> bool:
    if city.geo_level == City.GeoLevel.REGION:
        return True
    return bool(REGION_SUFFIX_RE.search(city.name or ""))


class Command(BaseCommand):
    help = (
        "Из адресов учреждений (улица…, Янаул) создать города-населённые пункты "
        "и переназначить facilities с «ведерных» регионов."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Макс. facilities (0 = все)")
        parser.add_argument(
            "--only-region-buckets",
            action="store_true",
            default=True,
            help="Только facilities, привязанные к области/республике",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = int(options["limit"] or 0)

        qs = MedicalFacility.objects.filter(is_active=True).select_related("city")
        if options["only_region_buckets"]:
            qs = qs.filter(
                Q(city__geo_level=City.GeoLevel.REGION)
                | Q(city__name__icontains="область")
                | Q(city__name__icontains="край")
                | Q(city__name__icontains="республика")
                | Q(city__name__icontains="округ")
            )
        if limit > 0:
            qs = qs[:limit]

        created_cities = 0
        moved = 0
        skipped = 0
        city_cache: dict[str, City] = {}

        with transaction.atomic():
            for fac in qs.iterator(chunk_size=500):
                if not is_region_bucket_city(fac.city):
                    skipped += 1
                    continue
                settlement = settlement_from_address(fac.address or "")
                if not settlement:
                    skipped += 1
                    continue
                key = settlement.casefold()
                city = city_cache.get(key)
                if city is None:
                    city = City.objects.filter(name__iexact=settlement).first()
                    if city is None:
                        if dry_run:
                            created_cities += 1
                            city_cache[key] = City(name=settlement, geo_level=City.GeoLevel.CITY, sort_order=0)
                            city = city_cache[key]
                        else:
                            city = City.objects.create(
                                name=settlement,
                                geo_level=City.GeoLevel.CITY,
                                sort_order=0,
                            )
                            created_cities += 1
                            city_cache[key] = city
                    else:
                        city_cache[key] = city

                if city.pk and fac.city_id == city.pk:
                    skipped += 1
                    continue

                if not dry_run and city.pk:
                    fac.city = city
                    fac.save(update_fields=["city", "updated_at"])
                moved += 1

            if dry_run:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}cities_created={created_cities} facilities_moved={moved} skipped={skipped}"
            )
        )
        # Smoke: Янаул
        yanaul = City.objects.filter(name__iexact="Янаул").first()
        if yanaul:
            n = MedicalFacility.objects.filter(city=yanaul, is_active=True).count()
            self.stdout.write(f"Янаул id={yanaul.id} facilities={n}")
        else:
            self.stdout.write(self.style.WARNING("Янаул still missing after pass"))
