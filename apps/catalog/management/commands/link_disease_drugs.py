from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.catalog.importers.catalog_importer import _upsert_disease
from apps.catalog.importers.disease_drug_rules import (
    BRAND_TO_INGREDIENT,
    COMBO_INGREDIENT_TOKENS,
    COMMON_DISEASES,
    DISEASE_DRUG_RULES,
    drugs_for_mkb_code,
    extract_mkb_code,
)
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

        all_drugs = list(Drug.objects.all())
        drugs_by_name = {d.name.lower(): d for d in all_drugs}

        # Индекс: токен МНН → все препараты, в названии которых есть токен
        # (Парацетамол, Парацетамол-СЗ, Ибупрофен + Парацетамол …).
        token_index: dict[str, list[Drug]] = {t: [] for t in COMBO_INGREDIENT_TOKENS}
        contains_cache: dict[str, list[Drug]] = {}

        for drug in all_drugs:
            name_l = (drug.name or "").lower()
            for token in COMBO_INGREDIENT_TOKENS:
                if token in name_l:
                    token_index[token].append(drug)

        def find_drugs(name: str) -> list[Drug]:
            """Точное совпадение + все варианты с МНН/токеном в названии."""
            key = (name or "").strip().lower()
            if not key:
                return []
            found: dict[int, Drug] = {}
            exact = drugs_by_name.get(key)
            if exact:
                found[exact.id] = exact
            if key in token_index:
                for d in token_index[key]:
                    found[d.id] = d
                return list(found.values())
            if key not in contains_cache:
                contains_cache[key] = [
                    d for d in all_drugs if key in (d.name or "").lower()
                ]
            for d in contains_cache[key]:
                found[d.id] = d
            return list(found.values())

        links = 0
        diseases_touched = 0

        qs = Disease.objects.all()
        if only_empty:
            qs = qs.annotate(n=Count("drugs")).filter(n=0)

        for disease in qs.iterator(chunk_size=500):
            name_l = (disease.name or "").lower()
            matched: dict[int, Drug] = {}

            def _add_name(dn: str) -> None:
                for drug in find_drugs(dn):
                    matched[drug.id] = drug

            # 1) По ключевым словам в названии
            for needle, drug_names in DISEASE_DRUG_RULES:
                if needle in name_l:
                    for dn in drug_names:
                        _add_name(dn)

            # 2) По коду МКБ-10
            code = extract_mkb_code(disease.description) or extract_mkb_code(disease.name)
            for dn in drugs_for_mkb_code(code):
                _add_name(dn)

            if not matched:
                continue
            diseases_touched += 1
            if dry_run:
                links += len(matched)
                continue
            before = disease.drugs.count()
            disease.drugs.add(*matched.values())
            links += max(0, disease.drugs.count() - before)

        # 3) Бренды / комбо без болезней → болезни базового МНН
        combo_links = self._link_orphan_drugs(
            all_drugs,
            token_index,
            dry_run=dry_run,
        )

        prefix = "[dry-run] " if dry_run else ""
        with_drugs = Disease.objects.annotate(n=Count("drugs")).filter(n__gt=0).count()
        drugs_with = Drug.objects.annotate(n=Count("diseases")).filter(n__gt=0).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Болезни +{created_diseases}; связей ~{links}; orphan/combo +{combo_links}; "
                f"болезней с препаратами={with_drugs}; лекарств с болезнями={drugs_with}"
            )
        )
        if dry_run:
            transaction.set_rollback(True)

    def _link_orphan_drugs(
        self,
        all_drugs: list[Drug],
        token_index: dict[str, list[Drug]],
        *,
        dry_run: bool,
    ) -> int:
        """Препараты без болезней получают болезни «базового» МНН / бренда."""
        # Базовые заболевания по каждому МНН-токену (берём у эталонного препарата).
        base_disease_ids: dict[str, list[int]] = {}
        for token, group in token_index.items():
            if not group:
                continue
            # Предпочитаем точное имя токена, иначе любой уже связанный
            preferred = next(
                (d for d in group if d.name.lower() == token),
                None,
            )
            candidates = [preferred] if preferred else group
            for d in candidates:
                ids = list(d.diseases.values_list("id", flat=True)[:200])
                if ids:
                    base_disease_ids[token] = ids
                    break
            # Если у точной группы ещё нет — собрать union по всей группе
            if token not in base_disease_ids:
                union: set[int] = set()
                for d in group:
                    union.update(d.diseases.values_list("id", flat=True)[:50])
                    if len(union) >= 80:
                        break
                if union:
                    base_disease_ids[token] = list(union)

        combo_links = 0
        linked_ids = set(
            Drug.objects.annotate(n=Count("diseases"))
            .filter(n__gt=0)
            .values_list("id", flat=True)
        )
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            name_l = (drug.name or "").lower()
            wanted: set[int] = set()

            for token, disease_ids in base_disease_ids.items():
                if token in name_l:
                    wanted.update(disease_ids)

            for brand, token in BRAND_TO_INGREDIENT.items():
                if brand in name_l and token in base_disease_ids:
                    wanted.update(base_disease_ids[token])

            if not wanted:
                continue
            if dry_run:
                combo_links += len(wanted)
                continue
            drug.diseases.add(*wanted)
            combo_links += len(wanted)
        return combo_links
