"""Parse drug analogs from vidal.ru (ТЗ §8.2.3)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.medic.importers.vidal_parser import parse_vidal_analogs


class Command(BaseCommand):
    help = "Fetch drug analog names from vidal.ru and store in DrugAnalog."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Max drugs to process")
        parser.add_argument("--drug-id", type=int, action="append", dest="drug_ids", help="Specific drug PK")
        parser.add_argument("--delay", type=float, default=1.0, help="Delay between HTTP requests")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = parse_vidal_analogs(
            drug_ids=options["drug_ids"],
            limit=options["limit"],
            delay_sec=options["delay"],
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix}Processed {result.drugs_processed} drugs; "
            f"analogs +{result.analogs_created} ~{result.analogs_updated}"
        )
        for err in result.errors[:25]:
            self.stdout.write(self.style.WARNING(err))
