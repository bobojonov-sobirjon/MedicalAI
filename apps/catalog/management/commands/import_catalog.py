"""Import catalog CSV files (ТЗ §5.6, §5.7, §7.11)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.importers.catalog_importer import import_catalog_from_files
from apps.core.csv_import import resolve_data_path


class Command(BaseCommand):
    help = "Import diseases, drugs, symptoms and disease↔drug links from CSV files."

    def add_arguments(self, parser):
        parser.add_argument("--diseases", default="diseases.csv", help="CSV path for diseases")
        parser.add_argument("--drugs", default="drugs.csv", help="CSV path for drugs")
        parser.add_argument("--symptoms", default="symptoms_extra.csv", help="CSV path for extra symptoms")
        parser.add_argument("--links", default="disease_drug_links.csv", help="CSV path for M2M links")
        parser.add_argument("--dry-run", action="store_true", help="Validate without writing to DB")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        paths = {
            "diseases": resolve_data_path(options["diseases"], base=base),
            "drugs": resolve_data_path(options["drugs"], base=base),
            "symptoms": resolve_data_path(options["symptoms"], base=base),
            "links": resolve_data_path(options["links"], base=base),
        }
        for label, path in paths.items():
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"Skip {label}: file not found ({path})"))
                paths[label] = None

        result = import_catalog_from_files(
            diseases_path=paths["diseases"],
            drugs_path=paths["drugs"],
            symptoms_path=paths["symptoms"],
            links_path=paths["links"],
            dry_run=options["dry_run"],
        )

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix}Diseases +{result.diseases_created} ~{result.diseases_updated}; "
            f"Drugs +{result.drugs_created} ~{result.drugs_updated}; "
            f"Symptoms +{result.symptoms_created} ~{result.symptoms_updated}; "
            f"Links +{result.links_created} (skipped {result.links_skipped})"
        )
        for err in result.errors[:30]:
            self.stdout.write(self.style.WARNING(err))
        if len(result.errors) > 30:
            self.stdout.write(self.style.WARNING(f"... and {len(result.errors) - 30} more errors"))
