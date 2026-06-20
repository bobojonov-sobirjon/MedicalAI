"""Import cities and medical facilities from CSV (ТЗ §5.8, §7.13)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.csv_import import resolve_data_path
from apps.medic.importers.geo_importer import import_cities_csv, import_facilities_csv, import_facilities_json


class Command(BaseCommand):
    help = "Import Russian cities and medical facilities (Yandex/2GIS CSV format)."

    def add_arguments(self, parser):
        parser.add_argument("--cities", default="cities_russia.csv", help="CSV with city names")
        parser.add_argument("--facilities", default="facilities.csv", help="CSV with pharmacies/hospitals")
        parser.add_argument("--facilities-json", default="", help="JSON file (Yandex Disk export)")
        parser.add_argument("--cities-only", action="store_true")
        parser.add_argument("--facilities-only", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        cities_path = resolve_data_path(options["cities"], base=base)
        facilities_path = resolve_data_path(options["facilities"], base=base)
        dry_run = options["dry_run"]

        with transaction.atomic():
            if not options["facilities_only"]:
                if cities_path.exists():
                    city_result = import_cities_csv(cities_path, dry_run=dry_run)
                    self.stdout.write(
                        f"Cities +{city_result.cities_created} ~{city_result.cities_updated}"
                    )
                    for err in city_result.errors[:20]:
                        self.stdout.write(self.style.WARNING(err))
                else:
                    self.stdout.write(self.style.WARNING(f"Cities file not found: {cities_path}"))

            if not options["cities_only"]:
                if options["facilities_json"]:
                    json_path = resolve_data_path(options["facilities_json"], base=base)
                    if json_path.exists():
                        fac_result = import_facilities_json(json_path, dry_run=dry_run)
                        self.stdout.write(
                            f"Facilities (JSON) +{fac_result.facilities_created} "
                            f"~{fac_result.facilities_updated} skipped={fac_result.facilities_skipped}"
                        )
                    else:
                        self.stdout.write(self.style.WARNING(f"JSON not found: {json_path}"))
                elif facilities_path.exists():
                    fac_result = import_facilities_csv(facilities_path, dry_run=dry_run)
                    self.stdout.write(
                        f"Facilities +{fac_result.facilities_created} "
                        f"~{fac_result.facilities_updated} skipped={fac_result.facilities_skipped}"
                    )
                    for err in fac_result.errors[:20]:
                        self.stdout.write(self.style.WARNING(err))
                else:
                    self.stdout.write(self.style.WARNING(f"Facilities file not found: {facilities_path}"))

            if dry_run:
                transaction.set_rollback(True)
