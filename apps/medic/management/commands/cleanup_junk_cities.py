from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.medic.city_quality import (
    curated_major_city_names,
    is_curated_major_city,
    is_osm_junk_city,
    latin_city_to_cyrillic,
)
from apps.medic.importers.city_normalize import clean_city_label
from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.models import City, MedicalFacility


class Command(BaseCommand):
    help = (
        "Удалить OSM-мусорные города. С --force: перепривязать объекты "
        "к крупному городу/региону и удалить junk (даже если есть facilities)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перепривязать facilities с junk-городов и удалить junk.",
        )
        parser.add_argument("--json", default="data/exports/osm_facilities.json")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        base = Path(settings.BASE_DIR)
        json_path = base / options["json"] if not Path(options["json"]).is_absolute() else Path(options["json"])

        by_external: dict[str, dict] = {}
        if json_path.exists():
            for row in load_facilities_json(json_path):
                eid = str(row.get("external_id") or "").strip()
                if eid:
                    by_external[eid] = row

        curated = curated_major_city_names()
        region_cities = {
            c.name: c
            for c in City.objects.filter(geo_level=City.GeoLevel.REGION)
        }

        renamed = 0
        deleted = 0
        relinked = 0
        skipped = 0

        for city in list(City.objects.all().order_by("id")):
            alias = latin_city_to_cyrillic(city.name)
            if alias:
                target = City.objects.filter(name__iexact=alias).first()
                if target and target.id != city.id:
                    if not dry_run:
                        n = MedicalFacility.objects.filter(city_id=city.id).update(city_id=target.id)
                        relinked += n
                        city.delete()
                    deleted += 1
                    self.stdout.write(f"  merge {city.name} -> {alias}")
                elif not target and not dry_run:
                    city.name = alias
                    city.save(update_fields=["name"])
                    renamed += 1
                continue

            if is_curated_major_city(city.name):
                continue
            if city.geo_level == City.GeoLevel.REGION:
                continue
            if not is_osm_junk_city(city) and city.sort_order and city.sort_order > 0:
                continue
            if not is_osm_junk_city(city) and city.name in curated:
                continue

            fac_qs = MedicalFacility.objects.filter(city_id=city.id)
            fac_count = fac_qs.count()
            if fac_count and not force:
                skipped += 1
                continue

            if fac_count and force:
                for fac in fac_qs.iterator(chunk_size=200):
                    target_city = None
                    row = by_external.get(str(fac.external_id or ""))
                    if row:
                        region = clean_city_label(str(row.get("region_name") or ""))
                        if region and region in region_cities:
                            target_city = region_cities[region]
                        else:
                            candidate = clean_city_label(
                                str(row.get("city_name") or row.get("city") or "")
                            )
                            if candidate and is_curated_major_city(candidate):
                                target_city = City.objects.filter(name__iexact=candidate).first()

                    if target_city is None:
                        for rname, rcity in region_cities.items():
                            if rname.lower() in (fac.address or "").lower():
                                target_city = rcity
                                break

                    if target_city is None:
                        target_city = next(iter(region_cities.values()), None)

                    if target_city and target_city.id != city.id:
                        if not dry_run:
                            fac.city = target_city
                            fac.save(update_fields=["city", "updated_at"])
                        relinked += 1

            if not dry_run:
                if not MedicalFacility.objects.filter(city_id=city.id).exists():
                    city.delete()
                    deleted += 1
                else:
                    skipped += 1
            else:
                deleted += 1

        if not dry_run:
            for i, name in enumerate(sorted(curated), start=1):
                City.objects.filter(name__iexact=name).update(
                    geo_level=City.GeoLevel.CITY,
                    sort_order=i,
                )

        prefix = "[dry-run] " if dry_run else ""
        major = City.objects.filter(geo_level=City.GeoLevel.CITY, sort_order__gt=0).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Города: удалено {deleted}, переименовано {renamed}, "
                f"перепривязано {relinked}, skip={skipped}. "
                f"Крупных в picker: {major}. Всего City: {City.objects.count()}"
            )
        )
        if dry_run:
            transaction.set_rollback(True)
