"""Import parsed catalog JSON into Disease / Drug models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from apps.catalog.importers.catalog_importer import (
    CatalogImportResult,
    _upsert_disease,
    _upsert_drug,
    import_disease_drug_links_csv,
)
from apps.catalog.importers.catalog_json import load_catalog_json


@dataclass
class ParsedCatalogImportResult:
    diseases: CatalogImportResult = field(default_factory=CatalogImportResult)
    drugs: CatalogImportResult = field(default_factory=CatalogImportResult)


def import_diseases_json(path: Path, *, dry_run: bool = False) -> CatalogImportResult:
    result = CatalogImportResult()
    for row in load_catalog_json(path):
        name = row.get("name") or ""
        description = row.get("description") or ""
        status, _ = _upsert_disease(name, description, dry_run=dry_run)
        if status == "created":
            result.diseases_created += 1
        elif status == "updated":
            result.diseases_updated += 1
    return result


def import_drugs_json(path: Path, *, dry_run: bool = False) -> CatalogImportResult:
    result = CatalogImportResult()
    for row in load_catalog_json(path):
        name = row.get("name") or ""
        description = row.get("description") or ""
        dosage = row.get("dosage") or ""
        instructions = row.get("instructions") or ""
        status, _ = _upsert_drug(name, description, dosage, dry_run=dry_run, instructions=instructions)
        if status == "created":
            result.drugs_created += 1
        elif status == "updated":
            result.drugs_updated += 1
    return result


@transaction.atomic
def import_parsed_catalog(
    *,
    diseases_path: Path | None = None,
    drugs_path: Path | None = None,
    links_path: Path | None = None,
    dry_run: bool = False,
) -> ParsedCatalogImportResult:
    total = ParsedCatalogImportResult()
    if diseases_path and diseases_path.exists():
        total.diseases = import_diseases_json(diseases_path, dry_run=dry_run)
    if drugs_path and drugs_path.exists():
        total.drugs = import_drugs_json(drugs_path, dry_run=dry_run)
    if links_path and links_path.exists():
        total.drugs.merge(import_disease_drug_links_csv(links_path, dry_run=dry_run))
    if dry_run:
        transaction.set_rollback(True)
    return total
