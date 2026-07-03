"""Remove junk cities (mikrorayon/ko'cha) and re-link facilities from OSM JSON."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.medic.importers.city_normalize import is_blocked_city_name, pick_city_name_for_facility_row
from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.importers.geo_importer import _get_or_create_city
from apps.medic.models import City, MedicalFacility


class Command(BaseCommand):
    help = "Delete invalid City rows (mahalla/ko'cha) and fix facility city links from OSM JSON."

    def add_arguments(self, parser):
        parser.add_argument("--json", default="data/exports/osm_facilities.json")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--delete-invalid-cities", action="store_true", default=True)

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        json_path = base / options["json"] if not Path(options["json"]).is_absolute() else Path(options["json"])
        dry_run = options["dry_run"]

        by_external: dict[str, dict] = {}
        if json_path.exists():
            for row in load_facilities_json(json_path):
                source = (row.get("external_source") or "osm").strip()
                eid = str(row.get("external_id") or "")
                if eid:
                    by_external[f"{source}:{eid}"] = row
            self.stdout.write(f"JSON: {len(by_external)} yozuv")
        else:
            self.stdout.write(self.style.WARNING(f"JSON topilmadi: {json_path} — faqat noto'g'ri City o'chiriladi"))

        invalid_cities = [c for c in City.objects.all() if is_blocked_city_name(c.name)]
        self.stdout.write(f"Noto'g'ri City: {len(invalid_cities)} ta")

        fixed = 0
        deleted_cities = 0
        skipped = 0

        with transaction.atomic():
            for city in invalid_cities:
                facilities = list(MedicalFacility.objects.filter(city=city))
                for fac in facilities:
                    key = f"{fac.external_source}:{fac.external_id}"
                    row = by_external.get(key) or {
                        "city_name": city.name,
                        "region_name": "",
                        "external_source": fac.external_source,
                        "external_id": fac.external_id,
                    }
                    new_name = pick_city_name_for_facility_row(row)
                    if not new_name:
                        skipped += 1
                        continue
                    new_city = _get_or_create_city(new_name, dry_run=dry_run)
                    if new_city is None:
                        if dry_run:
                            fixed += 1
                        else:
                            skipped += 1
                        continue
                    if not dry_run:
                        fac.city = new_city
                        fac.save(update_fields=["city", "updated_at"])
                    fixed += 1

                if options["delete_invalid_cities"]:
                    if not dry_run and not MedicalFacility.objects.filter(city=city).exists():
                        city.delete()
                        deleted_cities += 1
                    elif dry_run:
                        deleted_cities += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}"
                f"Muassasa city tuzatildi: {fixed}, skip={skipped}, "
                f"o'chirilgan City: {deleted_cities}"
            )
        )
        self.stdout.write(f"Qolgan City: {City.objects.count()}")
