"""Import diseases, drugs, symptoms and M2M links from CSV (ТЗ §5.6, §5.7, §7.11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from apps.catalog.models import Disease, Drug, Symptom
from apps.core.csv_import import iter_csv_rows, split_semicolon


@dataclass
class CatalogImportResult:
    diseases_created: int = 0
    diseases_updated: int = 0
    drugs_created: int = 0
    drugs_updated: int = 0
    symptoms_created: int = 0
    symptoms_updated: int = 0
    links_created: int = 0
    links_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: CatalogImportResult) -> None:
        for attr in (
            "diseases_created",
            "diseases_updated",
            "drugs_created",
            "drugs_updated",
            "symptoms_created",
            "symptoms_updated",
            "links_created",
            "links_skipped",
        ):
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))
        self.errors.extend(other.errors)


def _upsert_disease(
    name: str,
    description: str,
    *,
    dry_run: bool,
    instructions: str = "",
) -> tuple[str, Disease | None]:
    name = name.strip()
    if not name:
        return "skip", None
    existing = Disease.objects.filter(name__iexact=name).first()
    if existing:
        changed = False
        if description and (
            not existing.description
            or len(description.strip()) > len((existing.description or "").strip())
        ):
            existing.description = description
            changed = True
        if instructions and (
            not getattr(existing, "instructions", "")
            or len(instructions.strip()) > len((getattr(existing, "instructions", "") or "").strip())
        ):
            existing.instructions = instructions
            changed = True
        if changed and not dry_run:
            fields = ["description", "updated_at"]
            if hasattr(existing, "instructions"):
                fields.insert(1, "instructions")
            existing.save(update_fields=fields)
        return "updated" if changed else "exists", existing
    if dry_run:
        return "created", None
    kwargs = {"name": name, "description": description}
    if instructions:
        kwargs["instructions"] = instructions
    obj = Disease.objects.create(**kwargs)
    return "created", obj


def _upsert_drug(
    name: str,
    description: str,
    dosage: str,
    *,
    dry_run: bool,
    instructions: str = "",
) -> tuple[str, Drug | None]:
    name = name.strip()
    if not name:
        return "skip", None
    existing = Drug.objects.filter(name__iexact=name).first()
    if existing:
        changed = False
        if description and (
            not existing.description
            or len(description.strip()) > len((existing.description or "").strip())
        ):
            existing.description = description
            changed = True
        if instructions and (
            not existing.instructions
            or len(instructions.strip()) > len((existing.instructions or "").strip())
        ):
            existing.instructions = instructions
            changed = True
        if dosage and existing.dosage != dosage:
            existing.dosage = dosage
            changed = True
        if changed and not dry_run:
            existing.save(update_fields=["description", "instructions", "dosage", "updated_at"])
        return "updated" if changed else "exists", existing
    if dry_run:
        return "created", None
    obj = Drug.objects.create(
        name=name,
        description=description,
        instructions=instructions,
        dosage=dosage,
    )
    return "created", obj


def import_diseases_csv(path: Path, *, dry_run: bool = False) -> CatalogImportResult:
    result = CatalogImportResult()
    for row in iter_csv_rows(path):
        name = row.get("name") or row.get("disease") or row.get("название") or ""
        description = row.get("description") or row.get("описание") or ""
        status, _ = _upsert_disease(name, description, dry_run=dry_run)
        if status == "created":
            result.diseases_created += 1
        elif status == "updated":
            result.diseases_updated += 1
        elif status == "skip":
            result.errors.append(f"{path.name}: пустое название заболевания")
    return result


def import_drugs_csv(path: Path, *, dry_run: bool = False) -> CatalogImportResult:
    result = CatalogImportResult()
    for row in iter_csv_rows(path):
        name = row.get("name") or row.get("drug") or row.get("название") or ""
        description = row.get("description") or row.get("описание") or ""
        dosage = row.get("dosage") or row.get("дозировка") or ""
        instructions = row.get("instructions") or row.get("инструкция") or ""
        status, _ = _upsert_drug(name, description, dosage, dry_run=dry_run, instructions=instructions)
        if status == "created":
            result.drugs_created += 1
        elif status == "updated":
            result.drugs_updated += 1
        elif status == "skip":
            result.errors.append(f"{path.name}: пустое название лекарства")
    return result


def import_symptoms_csv(path: Path, *, dry_run: bool = False) -> CatalogImportResult:
    result = CatalogImportResult()
    for row in iter_csv_rows(path):
        name = row.get("name") or row.get("symptom") or row.get("название") or ""
        aliases_raw = row.get("aliases") or row.get("синонимы") or ""
        if not name:
            result.errors.append(f"{path.name}: пустое название симптома")
            continue
        aliases = ";".join(split_semicolon(aliases_raw))
        existing = Symptom.objects.filter(name__iexact=name).first()
        if existing:
            if aliases and existing.aliases != aliases and not dry_run:
                existing.aliases = aliases
                existing.save(update_fields=["aliases", "updated_at"])
                result.symptoms_updated += 1
            continue
        if dry_run:
            result.symptoms_created += 1
            continue
        Symptom.objects.create(name=name, aliases=aliases)
        result.symptoms_created += 1
    return result


def import_disease_drug_links_csv(path: Path, *, dry_run: bool = False) -> CatalogImportResult:
    result = CatalogImportResult()
    for row in iter_csv_rows(path):
        disease_name = row.get("disease_name") or row.get("disease") or row.get("заболевание") or ""
        drug_name = row.get("drug_name") or row.get("drug") or row.get("лекарство") or ""
        if not disease_name or not drug_name:
            result.errors.append(f"{path.name}: нужны disease_name и drug_name")
            continue
        disease = Disease.objects.filter(name__iexact=disease_name.strip()).first()
        drug = Drug.objects.filter(name__iexact=drug_name.strip()).first()
        if not disease or not drug:
            result.links_skipped += 1
            missing = []
            if not disease:
                missing.append(f"заболевание «{disease_name}»")
            if not drug:
                missing.append(f"лекарство «{drug_name}»")
            result.errors.append(f"пропуск связи: не найдено {', '.join(missing)}")
            continue
        if dry_run:
            result.links_created += 1
            continue
        if not drug.diseases.filter(pk=disease.pk).exists():
            drug.diseases.add(disease)
            result.links_created += 1
    return result


@transaction.atomic
def import_catalog_from_files(
    *,
    diseases_path: Path | None = None,
    drugs_path: Path | None = None,
    symptoms_path: Path | None = None,
    links_path: Path | None = None,
    dry_run: bool = False,
) -> CatalogImportResult:
    total = CatalogImportResult()
    if diseases_path and diseases_path.exists():
        total.merge(import_diseases_csv(diseases_path, dry_run=dry_run))
    if drugs_path and drugs_path.exists():
        total.merge(import_drugs_csv(drugs_path, dry_run=dry_run))
    if symptoms_path and symptoms_path.exists():
        total.merge(import_symptoms_csv(symptoms_path, dry_run=dry_run))
    if links_path and links_path.exists():
        total.merge(import_disease_drug_links_csv(links_path, dry_run=dry_run))
    if dry_run:
        transaction.set_rollback(True)
    return total
