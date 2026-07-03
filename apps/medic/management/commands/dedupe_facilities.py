"""Remove duplicate facilities (same city, name, and all data fields)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.medic.importers.facility_dedupe import dedupe_facilities_queryset
from apps.medic.models import MedicalFacility


class Command(BaseCommand):
    help = (
        "Delete duplicate facilities when kind, city, name, address, phone, "
        "hours and coordinates are all identical. Keeps the richest record."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--source", default="osm", help="external_source filter (empty = all)")
        parser.add_argument("--kind", default="", help="pharmacy or hospital")

    def handle(self, *args, **options):
        qs = MedicalFacility.objects.filter(is_active=True).select_related("city")
        source = (options.get("source") or "").strip()
        if source:
            qs = qs.filter(external_source=source)
        kind = (options.get("kind") or "").strip()
        if kind:
            qs = qs.filter(kind=kind)

        self.stdout.write(f"Tekshirilmoqda: {qs.count()} muassasa")

        with transaction.atomic():
            stats = dedupe_facilities_queryset(qs, dry_run=options["dry_run"])
            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Guruhlar: {stats.groups}, qoldirildi: {stats.kept}, "
                f"o'chirildi: {stats.removed}"
            )
        )
