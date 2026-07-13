from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.catalog.importers.catalog_importer import _upsert_disease
from apps.catalog.importers.disease_drug_rules import COMMON_DISEASES, DISEASE_DRUG_RULES
from apps.catalog.models import Disease, Drug


class Command(BaseCommand):
    help = (
        "Связать заболевания и лекарства по ключевым словам + добавить частые названия "
        "(холецистит и др.) для поиска в истории болезней."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--only-empty",
            action="store_true",
            help="Только болезни без лекарств / лекарства без болезней.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only_empty = options["only_empty"]

        created_diseases = 0
        for name, description in COMMON_DISEASES:
            status, _ = _upsert_disease(name, description, dry_run=dry_run)
            if status == "created":
                created_diseases += 1

        drugs_by_name = {d.name.lower(): d for d in Drug.objects.all()}
        # also map without case
        def find_drug(name: str) -> Drug | None:
            return drugs_by_name.get(name.lower()) or Drug.objects.filter(name__iexact=name).first()

        links = 0
        diseases_touched = 0

        qs = Disease.objects.all()
        if only_empty:
            qs = qs.annotate(n=Count("drugs")).filter(n=0)

        for disease in qs.iterator(chunk_size=500):
            name_l = (disease.name or "").lower()
            matched_drugs: list[Drug] = []
            for needle, drug_names in DISEASE_DRUG_RULES:
                if needle in name_l:
                    for dn in drug_names:
                        drug = find_drug(dn)
                        if drug and drug not in matched_drugs:
                            matched_drugs.append(drug)
            if not matched_drugs:
                continue
            diseases_touched += 1
            if dry_run:
                links += len(matched_drugs)
                continue
            before = disease.drugs.count()
            disease.drugs.add(*matched_drugs)
            links += max(0, disease.drugs.count() - before)

        prefix = "[dry-run] " if dry_run else ""
        with_drugs = Disease.objects.annotate(n=Count("drugs")).filter(n__gt=0).count()
        drugs_with = Drug.objects.annotate(n=Count("diseases")).filter(n__gt=0).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Болезни +{created_diseases}; связей ~{links}; "
                f"болезней с препаратами={with_drugs}; лекарств с болезнями={drugs_with}"
            )
        )
        if dry_run:
            transaction.set_rollback(True)
