"""Parse va import holatini tekshirish."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.csv_import import iter_csv_rows, resolve_data_path
from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.importers.yandex_parse_state import load_parse_state
from apps.medic.importers.yandex_facility_importer import load_import_state
from apps.medic.models import MedicalFacility


class Command(BaseCommand):
    help = "OSM parse/import tugagan-tugamaganini ko'rsatadi."

    def add_arguments(self, parser):
        parser.add_argument("--json", default="data/exports/osm_facilities.json")
        parser.add_argument("--parse-state", default="data/cache/osm_parse_state.json")
        parser.add_argument("--import-state", default="data/cache/osm_import_state.json")
        parser.add_argument("--regions-file", default="russia_regions.csv")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        json_path = base / options["json"] if not Path(options["json"]).is_absolute() else Path(options["json"])
        parse_state_path = base / options["parse_state"]
        import_state_path = base / options["import_state"]
        regions_path = resolve_data_path(options["regions_file"], base=base)

        total_regions = sum(1 for _ in iter_csv_rows(regions_path)) if regions_path.exists() else 0

        self.stdout.write(self.style.MIGRATE_HEADING("1) PARSE (Overpass -> JSON)"))
        if not json_path.exists():
            self.stdout.write(self.style.ERROR(f"  JSON yo'q: {json_path}"))
            json_count = 0
            meta = {}
        else:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            meta = raw.get("meta") or {}
            json_count = int(raw.get("count") or len(raw.get("facilities") or []))
            self.stdout.write(self.style.SUCCESS(f"  JSON bor: {json_path}"))
            self.stdout.write(f"  Yozuvlar: {json_count}")
            if meta.get("pharmacies") is not None:
                self.stdout.write(
                    f"  Apteka: {meta.get('pharmacies')} | Shifoxona: {meta.get('hospitals')}"
                )

        parse_state = load_parse_state(parse_state_path)
        done_regions = parse_state.get("completed_cities") or []
        done_count = len(done_regions)
        self.stdout.write(f"  Viloyatlar: {done_count}/{total_regions} tayyor")
        if total_regions and done_count >= total_regions:
            self.stdout.write(self.style.SUCCESS("  PARSE: TUGAGAN"))
        elif done_count:
            self.stdout.write(self.style.WARNING("  PARSE: DAVOM ETMOQDA (yoki to'xtatilgan)"))
            self.stdout.write(f"  Oxirgi viloyat: {parse_state.get('last_city', '?')}")
        else:
            self.stdout.write(self.style.ERROR("  PARSE: BOSHLANMAGAN yoki state yo'q"))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("2) IMPORT (JSON -> DB)"))
        imported_ids = load_import_state(import_state_path) if import_state_path.exists() else set()
        self.stdout.write(f"  Import state: {len(imported_ids)} ta ID")
        if not import_state_path.exists():
            self.stdout.write(self.style.WARNING("  import state fayli yo'q (--resume ishlatilmagan bo'lishi mumkin)"))

        db_qs = MedicalFacility.objects.filter(external_source="osm")
        db_total = db_qs.count()
        db_with_image = db_qs.exclude(image="").exclude(image__isnull=True).count()
        self.stdout.write(f"  DB (external_source=osm): {db_total} ta")
        self.stdout.write(f"  DB rasm bilan: {db_with_image} ta")
        self.stdout.write(
            f"  DB apteka: {db_qs.filter(kind=MedicalFacility.Kind.PHARMACY).count()} | "
            f"shifoxona: {db_qs.filter(kind=MedicalFacility.Kind.HOSPITAL).count()}"
        )

        # Haqiqiy tekshiruv: JSON dagi external_id lardan qanchasi DB da YO'Q.
        # (state/db son solishtirish noto'g'ri — JSON da dublikatlar bor.)
        json_ext_ids: set[str] = set()
        if json_path.exists():
            for row in load_facilities_json(json_path):
                ext = str(row.get("external_id") or "").strip()
                if ext:
                    json_ext_ids.add(ext)
        db_ext_ids = set(
            db_qs.exclude(external_id="").values_list("external_id", flat=True)
        )
        missing_ids = json_ext_ids - db_ext_ids if json_ext_ids else set()
        self.stdout.write(
            f"  JSON unikal ID: {len(json_ext_ids)} | DB da bor: {len(json_ext_ids) - len(missing_ids)} | yo'q: {len(missing_ids)}"
        )

        # dedupe_facilities birlashtirgan dublikatlar tabiiy ravishda "yo'q" bo'lib ko'rinadi.
        # Kichik farq (< 1%) — bu dublikatlar, qayta import kerak emas (aks holda halqa).
        dup_threshold = max(200, int(len(json_ext_ids) * 0.01)) if json_ext_ids else 0
        if json_ext_ids and not missing_ids:
            self.stdout.write(self.style.SUCCESS("  IMPORT: TUGAGAN (JSON dagi barcha ID DB da bor)"))
        elif missing_ids and len(missing_ids) <= dup_threshold:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  IMPORT: TUGAGAN — {len(missing_ids)} ta ID dublikat sifatida "
                    f"birlashtirilgan (dedupe). Qayta import KERAK EMAS."
                )
            )
        elif missing_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"  IMPORT: TO'LIQ EMAS — {len(missing_ids)} ta ID DB da yo'q.\n"
                    "  To'liq qayta yuklang (--resume EMAS, state buni o'tkazib yuboradi):\n"
                    "    python manage.py import_osm_facilities --no-images\n"
                    "    python manage.py dedupe_facilities\n"
                    "    python manage.py sync_osm_import_state"
                )
            )
        elif json_count and db_total == 0:
            self.stdout.write(self.style.ERROR("  IMPORT: BOSHLANMAGAN (DB bo'sh)"))
        else:
            self.stdout.write(self.style.WARNING("  IMPORT: tekshirib bo'lmadi (JSON yo'q)"))

        self.stdout.write("")
        self.stdout.write("Qayta davom ettirish:")
        if total_regions and done_count < total_regions:
            self.stdout.write("  python manage.py parse_osm_facilities --all-regions --resume")
        if missing_ids and len(missing_ids) > dup_threshold:
            self.stdout.write("  python manage.py import_osm_facilities --no-images")
