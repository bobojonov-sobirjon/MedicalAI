"""Deduplicate medical facilities with identical data in the same city."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from apps.medic.models import MedicalFacility


@dataclass
class DedupeStats:
    groups: int = 0
    removed: int = 0
    kept: int = 0


def facility_data_key(fac: MedicalFacility) -> tuple:
    """Same city + same name + all contact fields identical => duplicate."""
    lat = fac.latitude
    lon = fac.longitude
    return (
        fac.kind,
        fac.city_id,
        (fac.name or "").strip().casefold(),
        (fac.address or "").strip().casefold(),
        (fac.phone or "").strip(),
        (fac.hours_text or "").strip().casefold(),
        None if lat is None else str(lat),
        None if lon is None else str(lon),
    )


def facility_keep_score(fac: MedicalFacility) -> tuple:
    """Higher is better; first kept in group."""
    return (
        1 if fac.image else 0,
        1 if (fac.phone or "").strip() else 0,
        1 if (fac.address or "").strip() else 0,
        1 if (fac.hours_text or "").strip() else 0,
        1 if (fac.external_id or "").strip() else 0,
        -fac.id,
    )


def find_duplicate_groups(queryset) -> dict[tuple, list[MedicalFacility]]:
    groups: dict[tuple, list[MedicalFacility]] = defaultdict(list)
    for fac in queryset.iterator(chunk_size=2000):
        groups[facility_data_key(fac)].append(fac)
    return {key: items for key, items in groups.items() if len(items) > 1}


def dedupe_facilities_queryset(
    queryset,
    *,
    dry_run: bool = True,
) -> DedupeStats:
    stats = DedupeStats()
    duplicate_groups = find_duplicate_groups(queryset)

    for items in duplicate_groups.values():
        stats.groups += 1
        ordered = sorted(items, key=facility_keep_score, reverse=True)
        keeper = ordered[0]
        stats.kept += 1

        for duplicate in ordered[1:]:
            if not dry_run:
                if duplicate.image and not keeper.image:
                    keeper.image = duplicate.image
                    keeper.save(update_fields=["image", "updated_at"])
                duplicate.delete()
            stats.removed += 1

    return stats
