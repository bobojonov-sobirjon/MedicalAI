from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.importers.catalog_importer import (
    _upsert_disease,
    _upsert_drug,
    import_catalog_from_files,
)
from apps.catalog.importers.enriched_samples import DISEASE_ENRICHMENTS, DRUG_ENRICHMENTS
from apps.catalog.models import Disease, Drug
from apps.core.csv_import import resolve_data_path
from apps.catalog.importers.catalog_parsed_import import import_parsed_catalog


class Command(BaseCommand):
    help = (
        "Подготовка production-данных: очистка тестов, города, справочник болезней/лекарств, аптечка. "
        "Запускать на сервере после git pull и migrate."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--skip-cleanup", action="store_true")
        parser.add_argument("--skip-mkb10", action="store_true", help="Не импортировать МКБ-10.")
        parser.add_argument("--skip-osm-hint", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        base = Path(settings.BASE_DIR)

        self.stdout.write(self.style.MIGRATE_HEADING("1/7 Очистка тестовых болезней и лекарств"))
        if not options["skip_cleanup"]:
            call_command("cleanup_fake_catalog", dry_run=dry_run, aggressive=True)

        self.stdout.write(self.style.MIGRATE_HEADING("2/7 Очистка мусорных городов"))
        call_command("cleanup_junk_cities", dry_run=dry_run)

        self.stdout.write(self.style.MIGRATE_HEADING("3/7 Импорт городов России"))
        call_command("import_russia_cities", dry_run=dry_run)

        self.stdout.write(self.style.MIGRATE_HEADING("4/7 Справочник болезней (МКБ-10 + curated)"))
        if not options["skip_mkb10"]:
            mkb_json = base / "data" / "exports" / "diseases_mkb10.json"
            if not mkb_json.exists() and not dry_run:
                call_command("parse_mkb10_diseases", output=str(mkb_json))
            if mkb_json.exists():
                import_parsed_catalog(diseases_path=mkb_json, dry_run=dry_run)

        for name, description in DISEASE_ENRICHMENTS.items():
            _upsert_disease(name, description, dry_run=dry_run)

        diseases_csv = resolve_data_path("diseases.csv", base=base)
        if diseases_csv.exists():
            import_catalog_from_files(diseases_path=diseases_csv, dry_run=dry_run)

        if not dry_run:
            call_command("link_disease_drugs")
        else:
            call_command("link_disease_drugs", dry_run=True)

        self.stdout.write(self.style.MIGRATE_HEADING("5/7 Справочник лекарств + связи"))
        drugs_csv = resolve_data_path("drugs.csv", base=base)
        links_csv = resolve_data_path("disease_drug_links.csv", base=base)
        if drugs_csv.exists() or links_csv.exists():
            import_catalog_from_files(
                drugs_path=drugs_csv if drugs_csv.exists() else None,
                links_path=links_csv if links_csv.exists() else None,
                dry_run=dry_run,
            )

        for name, payload in DRUG_ENRICHMENTS.items():
            _upsert_drug(
                name,
                payload.get("description", ""),
                payload.get("dosage", ""),
                instructions=payload.get("instructions", ""),
                dry_run=dry_run,
            )

        vidal_json = base / "data" / "exports" / "drugs_vidal.json"
        if vidal_json.exists():
            import_parsed_catalog(drugs_path=vidal_json, dry_run=dry_run)
            self.stdout.write(f"  Vidal JSON: {vidal_json}")

        self.stdout.write(self.style.MIGRATE_HEADING("6/7 Аптечка -> справочник"))
        call_command("sync_cabinet_drugs", dry_run=dry_run)

        self.stdout.write(self.style.MIGRATE_HEADING("7/7 Статистика"))
        self.stdout.write(f"  Заболеваний: {Disease.objects.count()}")
        self.stdout.write(f"  Лекарств: {Drug.objects.count()}")

        if not options["skip_osm_hint"]:
            self.stdout.write("")
            self.stdout.write(
                "Больницы/аптеки (OSM): если в городе мало объектов, на сервере выполните:\n"
                "  python manage.py import_osm_facilities --resume\n"
                "  python manage.py fix_facility_cities --json data/exports/osm_facilities.json\n"
                "  python manage.py dedupe_facilities\n"
                "  python manage.py facility_data_stats --city 'Екатеринбург'"
            )

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING("[dry-run] Изменения отменены."))
        else:
            self.stdout.write(self.style.SUCCESS("prepare_prod_data завершён."))
