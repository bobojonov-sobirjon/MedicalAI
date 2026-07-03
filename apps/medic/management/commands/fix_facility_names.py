"""Fix ugly OSM facility names (03, +, etc.) in DB from export JSON."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.importers.facility_name_normalize import (
    finalize_facility_display_name,
    is_weak_facility_name,
    pick_facility_name_from_row,
)
from apps.medic.models import MedicalFacility


class Command(BaseCommand):
    help = "Normalize facility names in DB (prefer brand, drop 03/+ junk names)."

    def add_arguments(self, parser):
        parser.add_argument("--json", default="data/exports/osm_facilities.json")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--only-weak", action="store_true", default=False)
        parser.add_argument("--deactivate-unfixable", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        json_path = base / options["json"] if not Path(options["json"]).is_absolute() else Path(options["json"])
        if not json_path.exists():
            self.stdout.write(self.style.ERROR(f"JSON topilmadi: {json_path}"))
            return

        by_external: dict[str, dict] = {}
        for row in load_facilities_json(json_path):
            source = (row.get("external_source") or "osm").strip()
            eid = str(row.get("external_id") or "")
            if eid:
                by_external[f"{source}:{eid}"] = row

        self.stdout.write(f"JSON: {len(by_external)} yozuv")

        qs = MedicalFacility.objects.filter(external_source="osm").select_related("city")
        if options["only_weak"]:
            ids = [f.id for f in qs if is_weak_facility_name(f.name)]
            qs = MedicalFacility.objects.filter(id__in=ids).select_related("city")
        self.stdout.write(f"Tekshiriladi: {qs.count()} muassasa")

        updated = 0
        deactivated = 0
        unchanged = 0

        with transaction.atomic():
            for fac in qs.iterator(chunk_size=500):
                key = f"{fac.external_source}:{fac.external_id}"
                row = by_external.get(key) or {
                    "kind": fac.kind,
                    "name": fac.name,
                    "city_name": fac.city.name if fac.city_id else "",
                    "address": fac.address,
                    "latitude": fac.latitude,
                    "longitude": fac.longitude,
                    "external_source": fac.external_source,
                    "external_id": fac.external_id,
                }
                picked = pick_facility_name_from_row(row, kind=fac.kind)
                new_name = finalize_facility_display_name(picked or fac.name, kind=fac.kind)
                if not new_name or new_name == fac.name:
                    if options["deactivate_unfixable"] and is_weak_facility_name(fac.name):
                        if not options["dry_run"]:
                            fac.is_active = False
                            fac.save(update_fields=["is_active", "updated_at"])
                        deactivated += 1
                    else:
                        unchanged += 1
                    continue

                if not options["dry_run"]:
                    fac.name = new_name[:255]
                    fac.is_active = True
                    fac.save(update_fields=["name", "is_active", "updated_at"])
                updated += 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Yangilandi: {updated}, o'chirildi (inactive): {deactivated}, "
                f"o'zgarmadi: {unchanged}"
            )
        )
