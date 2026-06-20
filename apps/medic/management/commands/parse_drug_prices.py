"""Parse drug prices from zhivika.ru (ТЗ §8.2.3)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.medic.importers.zhivika_parser import parse_zhivika_prices


class Command(BaseCommand):
    help = "Fetch prices from zhivika.ru for DrugAnalog rows (or drugs)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=30)
        parser.add_argument("--drug-id", type=int, action="append", dest="drug_ids")
        parser.add_argument("--include-drugs", action="store_true", help="Parse main drugs, not only analogs")
        parser.add_argument("--delay", type=float, default=1.0)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = parse_zhivika_prices(
            drug_ids=options["drug_ids"],
            analogs_only=not options["include_drugs"],
            limit=options["limit"],
            delay_sec=options["delay"],
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix}Processed {result.items_processed}; prices updated {result.prices_updated}"
        )
        for err in result.errors[:25]:
            self.stdout.write(self.style.WARNING(err))
