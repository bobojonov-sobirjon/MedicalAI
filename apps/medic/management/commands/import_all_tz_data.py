"""
Import all TZ reference data from bundled CSV samples.

ТЗ: §5.6–5.8, §7.11, §7.13, §8.2.1, §8.2.3

  python manage.py import_all_tz_data
  python manage.py import_all_tz_data --with-parsers --parser-limit 10
  python manage.py import_all_tz_data --dry-run
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.catalog.importers.catalog_importer import import_catalog_from_files
from apps.core.csv_import import resolve_data_path
from apps.medic.importers.geo_importer import import_cities_csv, import_facilities_csv
from apps.medic.importers.vidal_parser import parse_vidal_analogs
from apps.medic.importers.zhivika_parser import parse_zhivika_prices


class Command(BaseCommand):
    help = "Import catalog + geo from data/samples and optionally run vidal/zhivika parsers."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--skip-catalog", action="store_true")
        parser.add_argument("--skip-geo", action="store_true")
        parser.add_argument("--with-parsers", action="store_true", help="Run vidal + zhivika parsers after import")
        parser.add_argument("--parser-limit", type=int, default=15)
        parser.add_argument("--parser-delay", type=float, default=1.2)

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        dry_run = options["dry_run"]

        if not options["skip_catalog"]:
            self.stdout.write("=== Catalog (diseases, drugs, symptoms, links) ===")
            catalog_result = import_catalog_from_files(
                diseases_path=resolve_data_path("diseases.csv", base=base),
                drugs_path=resolve_data_path("drugs.csv", base=base),
                symptoms_path=resolve_data_path("symptoms_extra.csv", base=base),
                links_path=resolve_data_path("disease_drug_links.csv", base=base),
                dry_run=dry_run,
            )
            self.stdout.write(
                f"Diseases +{catalog_result.diseases_created}; Drugs +{catalog_result.drugs_created}; "
                f"Symptoms +{catalog_result.symptoms_created}; Links +{catalog_result.links_created}"
            )

        if not options["skip_geo"]:
            self.stdout.write("=== Geo (cities, facilities) ===")
            cities_path = resolve_data_path("cities_russia.csv", base=base)
            facilities_path = resolve_data_path("facilities.csv", base=base)
            if cities_path.exists():
                city_result = import_cities_csv(cities_path, dry_run=dry_run)
                self.stdout.write(f"Cities +{city_result.cities_created}")
            if facilities_path.exists():
                fac_result = import_facilities_csv(facilities_path, dry_run=dry_run)
                self.stdout.write(
                    f"Facilities +{fac_result.facilities_created} ~{fac_result.facilities_updated}"
                )

        if options["with_parsers"] and not dry_run:
            self.stdout.write("=== Parsers (vidal.ru analogs) ===")
            vidal = parse_vidal_analogs(limit=options["parser_limit"], delay_sec=options["parser_delay"])
            self.stdout.write(
                f"Vidal: {vidal.drugs_processed} drugs, +{vidal.analogs_created} analogs"
            )
            self.stdout.write("=== Parsers (zhivika.ru prices) ===")
            zhivika = parse_zhivika_prices(limit=options["parser_limit"], delay_sec=options["parser_delay"])
            self.stdout.write(f"Zhivika: {zhivika.prices_updated} prices updated")

        self.stdout.write(self.style.SUCCESS("import_all_tz_data finished"))
