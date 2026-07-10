from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cabinet.models import CabinetItem
from apps.cabinet.services import match_drug_by_name
from apps.catalog.models import Drug


class Command(BaseCommand):
    help = "Привязать записи аптечки к справочнику лекарств по названию."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        linked = 0
        skipped = 0

        for item in CabinetItem.objects.select_related("drug").filter(drug__isnull=True):
            name = (item.custom_name or "").strip()
            if not name:
                skipped += 1
                continue
            drug, _ = match_drug_by_name(name)
            if not drug:
                skipped += 1
                continue
            if not dry_run:
                item.drug = drug
                item.save(update_fields=["drug", "updated_at"])
            linked += 1
            self.stdout.write(f"  {name} -> {drug.name}")

        for item in CabinetItem.objects.select_related("drug").exclude(drug__isnull=True):
            if item.drug and not item.drug.description and item.custom_name:
                drug, _ = match_drug_by_name(item.custom_name)
                if drug and drug.description and drug.id != item.drug_id:
                    if not dry_run:
                        item.drug = drug
                        item.save(update_fields=["drug", "updated_at"])
                    linked += 1

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Аптечка: привязано {linked}, пропущено {skipped}. "
                f"Справочник: {Drug.objects.count()} лекарств."
            )
        )
