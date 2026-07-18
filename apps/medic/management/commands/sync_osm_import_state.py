"""Rebuild OSM import state from DB so --resume imports missing facilities."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.importers.yandex_facility_importer import load_import_state, save_import_state
from apps.medic.models import MedicalFacility


class Command(BaseCommand):
    help = (
        "Синхронизировать osm_import_state.json с реальной БД. "
        "Удаляет из state ID, которых нет в DB — после этого "
        "`import_osm_facilities --resume` догрузит пропущенные аптеки/больницы."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", default="data/exports/osm_facilities.json")
        parser.add_argument("--state-file", default="data/cache/osm_import_state.json")
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Полностью очистить state (импорт начнётся с нуля, существующие обновятся).",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        state_path = base / options["state_file"]
        json_path = base / options["json"]

        db_ids = set(
            MedicalFacility.objects.filter(external_source="osm")
            .exclude(external_id="")
            .values_list("external_id", flat=True)
        )
        old_state = load_import_state(state_path) if state_path.exists() else set()

        if options["reset"]:
            new_state: set[str] = set()
        else:
            # Только то, что реально есть в БД
            new_state = {str(x) for x in db_ids}

        json_ids: set[str] = set()
        if json_path.exists():
            for row in load_facilities_json(json_path):
                eid = str(row.get("external_id") or "").strip()
                if eid:
                    json_ids.add(eid)

        missing = json_ids - new_state if json_ids else set()
        stale = old_state - new_state

        self.stdout.write(f"DB osm IDs: {len(db_ids)}")
        self.stdout.write(f"Eski state: {len(old_state)}")
        self.stdout.write(f"Yangi state: {len(new_state)}")
        self.stdout.write(f"State dan olib tashlanadi (DB da yo'q): {len(stale)}")
        self.stdout.write(f"JSON da bor, DB da yo'q (qayta import): {len(missing)}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("[dry-run] State o'zgartirilmadi."))
            return

        save_import_state(
            state_path,
            new_state,
            meta={
                "synced_from_db": True,
                "db_count": len(db_ids),
                "json_missing": len(missing),
            },
        )
        self.stdout.write(self.style.SUCCESS(f"State yangilandi: {state_path}"))
        self.stdout.write(
            "Endi ishga tushiring:\n"
            "  python manage.py import_osm_facilities --resume"
        )
