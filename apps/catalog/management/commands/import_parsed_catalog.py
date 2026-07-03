"""Import parsed diseases/drugs JSON into catalog models."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.importers.catalog_json import load_catalog_json
from apps.catalog.importers.catalog_parsed_import import import_parsed_catalog
from apps.core.csv_import import resolve_data_path


class Command(BaseCommand):
    help = "Import diseases_mkb10.json and/or drugs_vidal.json into DB."

    def add_arguments(self, parser):
        parser.add_argument("--diseases", default="data/exports/diseases_mkb10.json")
        parser.add_argument("--drugs", default="data/exports/drugs_vidal.json")
        parser.add_argument("--links", default="disease_drug_links.csv")
        parser.add_argument("--diseases-only", action="store_true")
        parser.add_argument("--drugs-only", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        diseases_path = base / options["diseases"] if not Path(options["diseases"]).is_absolute() else Path(options["diseases"])
        drugs_path = base / options["drugs"] if not Path(options["drugs"]).is_absolute() else Path(options["drugs"])
        links_path = resolve_data_path(options["links"], base=base)

        if options["diseases_only"]:
            drugs_path = None
            links_path = None
        if options["drugs_only"]:
            diseases_path = None

        for label, path in (("Diseases", diseases_path), ("Drugs", drugs_path)):
            if path and path.exists():
                self.stdout.write(f"{label}: {path} ({len(load_catalog_json(path))} yozuv)")
            elif path:
                self.stdout.write(self.style.WARNING(f"{label}: topilmadi {path}"))

        result = import_parsed_catalog(
            diseases_path=diseases_path if diseases_path and diseases_path.exists() else None,
            drugs_path=drugs_path if drugs_path and drugs_path.exists() else None,
            links_path=links_path if links_path and links_path.exists() else None,
            dry_run=options["dry_run"],
        )

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Kasalliklar +{result.diseases.diseases_created} "
                f"~{result.diseases.diseases_updated}; "
                f"Dorilar +{result.drugs.drugs_created} ~{result.drugs.drugs_updated}; "
                f"Links +{result.drugs.links_created}"
            )
        )
