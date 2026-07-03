"""Load Russian regions (viloyat) and cities from CSV into City."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.csv_import import iter_csv_rows, resolve_data_path
from apps.medic.importers.city_normalize import clean_city_label, infer_geo_level, is_blocked_city_name
from apps.medic.models import City


class Command(BaseCommand):
    help = "Import Russian regions and major cities into City (no streets/mahalla)."

    def add_arguments(self, parser):
        parser.add_argument("--regions-file", default="russia_regions.csv")
        parser.add_argument("--cities-file", default="cities_russia.csv")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        regions_path = resolve_data_path(options["regions_file"], base=base)
        cities_path = resolve_data_path(options["cities_file"], base=base)

        created = 0
        skipped = 0

        for path, level in ((regions_path, City.GeoLevel.REGION), (cities_path, City.GeoLevel.CITY)):
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"Skip: {path} not found"))
                continue
            for row in iter_csv_rows(path):
                name = clean_city_label(row.get("name") or row.get("city") or "")
                if not name or is_blocked_city_name(name):
                    skipped += 1
                    continue
                geo_level = level if level == City.GeoLevel.REGION else infer_geo_level(name)
                if City.objects.filter(name__iexact=name).exists():
                    if not options["dry_run"]:
                        City.objects.filter(name__iexact=name).update(geo_level=geo_level)
                    continue
                if options["dry_run"]:
                    created += 1
                    continue
                City.objects.create(name=name, geo_level=geo_level)
                created += 1

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Viloyat/shahar katalogi: +{created} yangi, skip={skipped}"
            )
        )
        self.stdout.write(
            f"Jami City: {City.objects.count()} "
            f"(viloyat {City.objects.filter(geo_level=City.GeoLevel.REGION).count()}, "
            f"shahar {City.objects.filter(geo_level=City.GeoLevel.CITY).count()}, "
            f"tuman {City.objects.filter(geo_level=City.GeoLevel.DISTRICT).count()})"
        )
