"""Импорт лекарств из выгрузки ГРЛС (Государственный реестр лекарственных средств).

1) Скачайте реестр с https://grls.rosminzdrav.ru/GRLS.aspx (Excel) или CSV.
2) Положите файл на сервер, например data/imports/grls.xlsx
3) Проверка (ничего не пишет):
     python manage.py import_grls_drugs --file data/imports/grls.xlsx
4) Импорт:
     python manage.py import_grls_drugs --file data/imports/grls.xlsx --apply
5) Связи болезнь↔лекарство:
     python manage.py link_disease_drugs
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.importers.grls_importer import import_grls_drugs
from apps.catalog.models import Drug


class Command(BaseCommand):
    help = "Import drugs from GRLS Excel/CSV export (official Minzdrav registry)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to GRLS .xlsx or .csv",
        )
        parser.add_argument("--apply", action="store_true", help="Save to DB (default: dry-run).")
        parser.add_argument("--limit", type=int, default=0, help="Limit unique trade names.")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        if not path.exists():
            raise CommandError(
                f"Файл не найден: {path}\n"
                "Скачайте выгрузку ГРЛС с https://grls.rosminzdrav.ru/GRLS.aspx "
                "и укажите --file ..."
            )

        dry_run = not options["apply"]
        self.stdout.write(f"GRLS файл: {path} ({'DRY-RUN' if dry_run else 'APPLY'})")
        try:
            stats = import_grls_drugs(path, dry_run=dry_run, limit=options["limit"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Строк={stats.rows_total}, уникальных названий={stats.unique_names}, "
                f"+{stats.created} ~{stats.updated}, "
                f"skip_empty={stats.skipped_empty}, skip_inactive={stats.skipped_inactive}"
            )
        )
        self.stdout.write(f"Всего Drug в БД: {Drug.objects.count()} (active={Drug.objects.filter(is_active=True).count()})")
        if dry_run:
            self.stdout.write("Для записи в БД добавьте --apply")
        else:
            self.stdout.write("Далее: python manage.py link_disease_drugs")
