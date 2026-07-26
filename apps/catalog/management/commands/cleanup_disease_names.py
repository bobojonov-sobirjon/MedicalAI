"""Rename Disease.name: strip English [brackets] / latin (parens), merge duplicates."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Disease
from apps.catalog.utils import clean_disease_display_name


class Command(BaseCommand):
    help = "Убрать английские пояснения из названий заболеваний ([herpes simplex] и т.п.)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        renamed = 0
        merged = 0
        skipped = 0

        for disease in Disease.objects.order_by("id").iterator(chunk_size=500):
            cleaned = clean_disease_display_name(disease.name)
            if not cleaned or cleaned == disease.name:
                continue
            cleaned = cleaned[:255]
            existing = (
                Disease.objects.filter(name__iexact=cleaned).exclude(pk=disease.pk).first()
            )
            if existing:
                if not dry_run:
                    existing.drugs.add(*disease.drugs.all())
                    disease.delete()
                merged += 1
                continue
            if dry_run:
                renamed += 1
                continue
            try:
                disease.name = cleaned
                disease.save(update_fields=["name"])
                renamed += 1
            except Exception:
                skipped += 1

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}renamed={renamed}, merged={merged}, skipped={skipped}"
            )
        )
        if dry_run:
            transaction.set_rollback(True)
