"""
МКБ-10 → JSON → DB (kasalliklar).

Terminal 1:
  python manage.py parse_mkb10_diseases

Terminal 2:
  python manage.py import_parsed_catalog --diseases-only
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.importers.catalog_parsed_import import import_diseases_json
from apps.catalog.importers.mkb10_parser import (
    DEFAULT_MKB10_CSV_URL,
    fetch_and_parse_mkb10,
    save_diseases_json,
)


class Command(BaseCommand):
    help = "Parse МКБ-10 (ICD-10) diseases to JSON and optionally import to DB."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default="", help="Local MKB CSV path")
        parser.add_argument("--csv-url", default=DEFAULT_MKB10_CSV_URL)
        parser.add_argument("--min-level", type=int, default=2, help="MKB hierarchy level (2+)")
        parser.add_argument("--output", default="data/exports/diseases_mkb10.json")
        parser.add_argument("--no-download", action="store_true")
        parser.add_argument("--import-db", action="store_true", help="Import to DB after parse")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        csv_path = Path(options["csv"]) if options["csv"] else base / "data" / "cache" / "mkb10.csv"
        output = base / options["output"] if not Path(options["output"]).is_absolute() else Path(options["output"])

        self.stdout.write("MKB-10 parse boshlandi...")
        items, stats = fetch_and_parse_mkb10(
            csv_path=csv_path,
            csv_url=options["csv_url"],
            min_level=int(options["min_level"]),
            download=not options["no_download"],
        )
        for err in stats.errors:
            self.stdout.write(self.style.ERROR(err))

        if not items:
            self.stdout.write(self.style.ERROR("Kasallik topilmadi"))
            return

        save_diseases_json(
            items,
            output,
            meta={
                "rows_total": stats.rows_total,
                "diseases_kept": stats.diseases_kept,
                "skipped": stats.skipped,
                "min_level": options["min_level"],
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"TUGADI: {len(items)} kasallik -> {output} "
                f"(CSV qator {stats.rows_total}, skip {stats.skipped})"
            )
        )

        if options["import_db"]:
            result = import_diseases_json(output, dry_run=options["dry_run"])
            prefix = "[dry-run] " if options["dry_run"] else ""
            self.stdout.write(
                f"{prefix}DB: +{result.diseases_created} ~{result.diseases_updated}"
            )
