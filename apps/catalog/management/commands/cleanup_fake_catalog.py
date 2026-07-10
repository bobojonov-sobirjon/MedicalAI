from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from pathlib import Path

from apps.catalog.data_quality import (
    FAKE_DESCRIPTION_RE,
    iter_fake_diseases,
    iter_fake_drugs,
)
from apps.catalog.models import Disease, Drug
from apps.core.csv_import import iter_csv_rows, resolve_data_path


class Command(BaseCommand):
    help = "Удалить тестовые (faker) болезни и лекарства из production."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--aggressive",
            action="store_true",
            help="Удалить также seed_demo болезни без МКБ-10 (не из diseases.csv).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        fake_diseases = {row.id: row for row in iter_fake_diseases()}
        fake_drugs = {row.id: row for row in iter_fake_drugs()}

        if options["aggressive"]:
            curated = set()
            path = resolve_data_path("diseases.csv", base=Path(settings.BASE_DIR))
            if path.exists():
                for row in iter_csv_rows(path):
                    name = (row.get("name") or "").strip()
                    if name:
                        curated.add(name)
            for row in Disease.objects.all().only("id", "name", "description"):
                if row.id in fake_diseases:
                    continue
                if row.name in curated:
                    continue
                desc = (row.description or "").strip()
                if desc.startswith("МКБ-10"):
                    continue
                if FAKE_DESCRIPTION_RE.search(desc) or len(desc) < 40:
                    fake_diseases[row.id] = row

        fake_diseases_list = list(fake_diseases.values())
        fake_drugs_list = list(fake_drugs.values())

        self.stdout.write(f"Найдено тестовых заболеваний: {len(fake_diseases_list)}")
        for row in fake_diseases_list[:20]:
            self.stdout.write(f"  - {row.name}")
        if len(fake_diseases_list) > 20:
            self.stdout.write(f"  ... и ещё {len(fake_diseases_list) - 20}")

        self.stdout.write(f"Найдено тестовых лекарств: {len(fake_drugs_list)}")
        for row in fake_drugs_list[:20]:
            self.stdout.write(f"  - {row.name}")
        if len(fake_drugs_list) > 20:
            self.stdout.write(f"  ... и ещё {len(fake_drugs_list) - 20}")

        if dry_run:
            self.stdout.write(self.style.WARNING("[dry-run] Удаление не выполнено."))
            return

        deleted_d = Disease.objects.filter(id__in=[x.id for x in fake_diseases_list]).delete()[0]
        deleted_r = Drug.objects.filter(id__in=[x.id for x in fake_drugs_list]).delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Удалено: заболеваний {deleted_d}, лекарств {deleted_r}"))
