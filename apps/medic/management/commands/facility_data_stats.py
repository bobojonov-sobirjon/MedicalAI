"""Show how complete facility data is (address, phone, hours)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.models import MedicalFacility


class Command(BaseCommand):
    help = "Report missing address/phone/hours in DB and optional OSM JSON."

    def add_arguments(self, parser):
        parser.add_argument("--json", default="")
        parser.add_argument("--source", default="osm")

    def handle(self, *args, **options):
        source = (options.get("source") or "").strip()
        qs = MedicalFacility.objects.all()
        if source:
            qs = qs.filter(external_source=source)

        total = qs.count()
        if not total:
            self.stdout.write("DB bo'sh")
            return

        with_address = qs.exclude(address="").count()
        with_phone = qs.exclude(phone="").count()
        with_hours = qs.exclude(hours_text="").count()
        with_image = qs.exclude(image="").exclude(image__isnull=True).count()
        with_coords = qs.filter(latitude__isnull=False, longitude__isnull=False).count()

        self.stdout.write(self.style.MIGRATE_HEADING("DB (MedicalFacility)"))
        self._print_block(
            total,
            {
                "Manzil (address)": with_address,
                "Telefon": with_phone,
                "Ish vaqti (hours)": with_hours,
                "Rasm": with_image,
                "Koordinata": with_coords,
            },
        )

        dup_groups = (
            qs.values("kind", "city_id", "name")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
            .count()
        )
        self.stdout.write(f"\nNom+shahar bir xil (>=2 yozuv): {dup_groups} guruh")

        json_path = (options.get("json") or "").strip()
        if json_path:
            path = Path(json_path)
            if not path.is_absolute():
                path = Path(settings.BASE_DIR) / path
            if path.exists():
                self._report_json(path)

    def _print_block(self, total: int, fields: dict[str, int]) -> None:
        for label, count in fields.items():
            pct = (count * 100.0 / total) if total else 0
            missing = total - count
            self.stdout.write(f"  {label}: {count}/{total} ({pct:.1f}%) — yo'q: {missing}")

    def _report_json(self, path: Path) -> None:
        rows = load_facilities_json(path)
        total = len(rows)
        if not total:
            return

        def has_field(key: str) -> int:
            return sum(1 for row in rows if str(row.get(key) or "").strip())

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"JSON ({path.name})"))
        self._print_block(
            total,
            {
                "Manzil": has_field("address"),
                "Telefon": has_field("phone"),
                "Ish vaqti": has_field("hours_text"),
                "Rasm URL": sum(
                    1
                    for row in rows
                    if str(row.get("image_url") or "").strip()
                    or (row.get("images") or [])
                ),
            },
        )
        self.stdout.write(
            "\nOSM da ko'p nuqtada faqat koordinata bor; manzil/telefon ixtiyoriy teglar."
        )
