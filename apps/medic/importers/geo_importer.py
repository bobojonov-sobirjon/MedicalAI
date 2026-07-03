"""Import cities and medical facilities (ТЗ §5.8, §7.13, §8.2.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from apps.core.csv_import import iter_csv_rows
from apps.medic.models import City, MedicalFacility

from .city_normalize import clean_city_label, infer_geo_level, is_blocked_city_name


@dataclass
class GeoImportResult:
    cities_created: int = 0
    cities_updated: int = 0
    facilities_created: int = 0
    facilities_updated: int = 0
    facilities_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_decimal(value: str) -> Decimal | None:
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _normalize_kind(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"pharmacy", "аптека", "drugstore"}:
        return MedicalFacility.Kind.PHARMACY
    if value in {"hospital", "больница", "clinic", "поликлиника"}:
        return MedicalFacility.Kind.HOSPITAL
    return value


def _get_or_create_city(
    name: str,
    *,
    dry_run: bool,
    geo_level: str | None = None,
) -> City | None:
    name = clean_city_label(name)
    if not name or is_blocked_city_name(name):
        return None
    existing = City.objects.filter(name__iexact=name).first()
    if existing:
        return existing
    if dry_run:
        return None
    level = geo_level or infer_geo_level(name)
    return City.objects.create(name=name, geo_level=level)


@transaction.atomic
def import_cities_csv(path: Path, *, dry_run: bool = False) -> GeoImportResult:
    result = GeoImportResult()
    for row in iter_csv_rows(path):
        name = row.get("name") or row.get("city") or row.get("город") or ""
        if not name:
            result.errors.append(f"{path.name}: пустое название города")
            continue
        sort_raw = row.get("sort_order") or row.get("порядок") or "0"
        try:
            sort_order = int(sort_raw)
        except ValueError:
            sort_order = 0
        existing = City.objects.filter(name__iexact=name).first()
        if existing:
            if sort_order and existing.sort_order != sort_order and not dry_run:
                existing.sort_order = sort_order
                existing.save(update_fields=["sort_order"])
                result.cities_updated += 1
            continue
        if dry_run:
            result.cities_created += 1
            continue
        City.objects.create(
            name=name,
            sort_order=sort_order,
            geo_level=infer_geo_level(name),
        )
        result.cities_created += 1
    if dry_run:
        transaction.set_rollback(True)
    return result


def _upsert_facility(row: dict[str, str], *, dry_run: bool) -> tuple[str, str | None]:
    kind = _normalize_kind(row.get("kind") or row.get("тип") or "")
    city_name = row.get("city_name") or row.get("city") or row.get("город") or ""
    name = row.get("name") or row.get("название") or ""
    if kind not in {MedicalFacility.Kind.PHARMACY, MedicalFacility.Kind.HOSPITAL}:
        return "skip", f"неизвестный тип: {kind or 'пусто'}"
    if not city_name or not name:
        return "skip", "нужны city и name"

    city = _get_or_create_city(city_name, dry_run=dry_run)
    if city is None and not dry_run:
        return "skip", f"город «{city_name}» не создан"

    external_source = (row.get("external_source") or row.get("источник") or "").strip()
    external_id = (row.get("external_id") or row.get("внешний_id") or "").strip()
    address = row.get("address") or row.get("адрес") or ""
    phone = row.get("phone") or row.get("телефон") or ""
    hours_text = row.get("hours_text") or row.get("часы") or row.get("hours") or ""
    description = row.get("description") or row.get("описание") or ""
    latitude = _parse_decimal(row.get("latitude") or row.get("широта") or "")
    longitude = _parse_decimal(row.get("longitude") or row.get("долгота") or "")

    existing = None
    if external_source and external_id:
        existing = MedicalFacility.objects.filter(
            external_source=external_source,
            external_id=external_id,
        ).first()
    if existing is None and city is not None:
        existing = MedicalFacility.objects.filter(
            kind=kind,
            city=city,
            name=name,
            address=address,
        ).first()

    if existing:
        if dry_run:
            return "updated", None
        changed_fields: list[str] = []
        for field_name, value in (
            ("phone", phone),
            ("hours_text", hours_text),
            ("description", description),
            ("latitude", latitude),
            ("longitude", longitude),
            ("external_source", external_source),
            ("external_id", external_id),
        ):
            if value and getattr(existing, field_name) != value:
                setattr(existing, field_name, value)
                changed_fields.append(field_name)
        if changed_fields:
            changed_fields.append("updated_at")
            existing.save(update_fields=changed_fields)
            return "updated", None
        return "exists", None

    if dry_run:
        return "created", None
    if city is None:
        return "skip", f"город «{city_name}»"
    MedicalFacility.objects.create(
        kind=kind,
        city=city,
        name=name,
        address=address,
        phone=phone,
        hours_text=hours_text,
        description=description,
        latitude=latitude,
        longitude=longitude,
        external_source=external_source,
        external_id=external_id,
    )
    return "created", None


@transaction.atomic
def import_facilities_csv(path: Path, *, dry_run: bool = False) -> GeoImportResult:
    result = GeoImportResult()
    for row in iter_csv_rows(path):
        status, err = _upsert_facility(row, dry_run=dry_run)
        if status == "created":
            result.facilities_created += 1
        elif status == "updated":
            result.facilities_updated += 1
        elif status == "exists":
            continue
        else:
            result.facilities_skipped += 1
            if err:
                result.errors.append(err)
    if dry_run:
        transaction.set_rollback(True)
    return result


@transaction.atomic
def import_facilities_json(path: Path, *, dry_run: bool = False) -> GeoImportResult:
    """Import facilities from JSON array (Yandex Disk / export format)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items") or raw.get("facilities") or []
    result = GeoImportResult()
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {
            "kind": str(item.get("kind") or item.get("type") or ""),
            "city_name": str(item.get("city_name") or item.get("city") or ""),
            "name": str(item.get("name") or item.get("title") or ""),
            "address": str(item.get("address") or ""),
            "phone": str(item.get("phone") or ""),
            "hours_text": str(item.get("hours_text") or item.get("hours") or ""),
            "latitude": str(item.get("latitude") or item.get("lat") or ""),
            "longitude": str(item.get("longitude") or item.get("lon") or item.get("lng") or ""),
            "external_source": str(item.get("external_source") or item.get("source") or "yandex"),
            "external_id": str(item.get("external_id") or item.get("id") or ""),
            "description": str(item.get("description") or ""),
        }
        status, err = _upsert_facility(row, dry_run=dry_run)
        if status == "created":
            result.facilities_created += 1
        elif status == "updated":
            result.facilities_updated += 1
        elif status == "exists":
            continue
        else:
            result.facilities_skipped += 1
            if err:
                result.errors.append(err)
    if dry_run:
        transaction.set_rollback(True)
    return result
