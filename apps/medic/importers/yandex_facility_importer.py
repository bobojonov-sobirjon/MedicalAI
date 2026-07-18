"""Import Yandex facilities JSON into DB with image download."""

from __future__ import annotations

import json
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

import requests
from django.core.files.base import ContentFile
from django.db import transaction

from apps.medic.models import MedicalFacility

from .geo_importer import _get_or_create_city, _normalize_kind
from .city_normalize import pick_city_name_for_facility_row
from .facilities_json import load_facilities_json
from .facility_image_resolver import resolve_facility_image_url

logger = logging.getLogger(__name__)

USER_AGENT = "MedicAI-FacilityImporter/1.0"


@dataclass
class YandexImportStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    skipped_no_image: int = 0
    images_saved: int = 0
    image_errors: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _pick_image_url(row: dict) -> str:
    url = (row.get("image_url") or "").strip()
    if url:
        return url
    images = row.get("images") or []
    if isinstance(images, list) and images:
        return str(images[0]).strip()
    return ""


def _extension_for_content(url: str, content_type: str) -> str:
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    lower = url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if lower.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    guessed = mimetypes.guess_extension(content_type or "")
    return guessed or ".jpg"


def download_facility_image(
    url: str,
    *,
    timeout: int = 25,
    session: requests.Session | None = None,
) -> tuple[bytes, str] | None:
    if not url or not url.startswith("http"):
        return None
    session = session or requests.Session()
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*"},
        )
        response.raise_for_status()
        content = response.content
        if len(content) < 200:
            return None
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "image" not in content_type and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            return None
        return content, _extension_for_content(url, content_type)
    except requests.RequestException as exc:
        logger.warning("image download failed %s: %s", url[:80], exc)
        return None


def load_import_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(x) for x in (data.get("imported_ids") or [])}
    except json.JSONDecodeError:
        return set()


def save_import_state(path: Path, imported_ids: set[str], *, meta: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "imported_ids": sorted(imported_ids),
        "count": len(imported_ids),
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _upsert_facility_row(
    row: dict,
    *,
    download_images: bool,
    require_image: bool,
    allow_static_map_fallback: bool,
    image_session: requests.Session,
    stats: YandexImportStats,
    skip_without_image: bool = True,
) -> bool:
    kind = _normalize_kind(row.get("kind") or "")
    city_name = pick_city_name_for_facility_row(
        row,
        region_fallback=str(row.get("region_name") or ""),
    )
    name = (row.get("name") or "").strip()
    external_source = (row.get("external_source") or "yandex").strip()
    external_id = str(row.get("external_id") or "").strip()

    if kind not in {MedicalFacility.Kind.PHARMACY, MedicalFacility.Kind.HOSPITAL}:
        stats.skipped += 1
        return False
    if not city_name or not name or not external_id:
        stats.skipped += 1
        return False

    city = _get_or_create_city(city_name, dry_run=False)
    if city is None:
        stats.skipped += 1
        return False

    address = (row.get("address") or "")[:512]
    phone = (row.get("phone") or "")[:64]
    hours_text = (row.get("hours_text") or row.get("hours") or "")[:255]
    description = (row.get("description") or "")[:2000]
    latitude = _parse_decimal(row.get("latitude"))
    longitude = _parse_decimal(row.get("longitude"))

    existing = MedicalFacility.objects.filter(
        external_source=external_source,
        external_id=external_id,
    ).first()
    if existing is None:
        existing = MedicalFacility.objects.filter(
            kind=kind,
            city=city,
            name=name,
            address=address,
        ).first()

    created = existing is None
    if created:
        facility = MedicalFacility(
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
            is_active=True,
        )
    else:
        facility = existing
        facility.kind = kind
        facility.city = city
        facility.name = name
        if address:
            facility.address = address
        if phone:
            facility.phone = phone
        if hours_text:
            facility.hours_text = hours_text
        if description:
            facility.description = description
        if latitude is not None:
            facility.latitude = latitude
        if longitude is not None:
            facility.longitude = longitude
        facility.external_source = external_source or facility.external_source
        facility.external_id = external_id or facility.external_id
        facility.is_active = True

    needs_image = require_image and not facility.image
    image_url = ""
    image_source = ""
    if download_images and (needs_image or (require_image and created)):
        image_url, image_source = resolve_facility_image_url(
            row,
            allow_static_map_fallback=allow_static_map_fallback,
        )
        if not image_url:
            # Нет источника картинки. Если разрешено — импортируем без картинки.
            if skip_without_image:
                stats.skipped += 1
                stats.skipped_no_image += 1
                return False
            stats.skipped_no_image += 1
        else:
            downloaded = download_facility_image(image_url, session=image_session)
            if not downloaded:
                # Скачивание не удалось (rate-limit/сеть). Не выбрасываем учреждение,
                # если skip_without_image=False — карту нарисует клиент по lat/lon.
                stats.image_errors += 1
                if skip_without_image:
                    stats.skipped += 1
                    stats.skipped_no_image += 1
                    return False
            else:
                content, ext = downloaded
                image_dir = (external_source or "facility").strip() or "facility"
                facility.image.save(f"{image_dir}/{external_id}{ext}", ContentFile(content), save=False)
                stats.images_saved += 1
                row["resolved_image_url"] = image_url
                row["resolved_image_source"] = image_source
    elif require_image and created and not facility.image and skip_without_image:
        stats.skipped += 1
        stats.skipped_no_image += 1
        return False

    facility.save()
    if created:
        stats.created += 1
    else:
        stats.updated += 1
    return True


def import_yandex_facilities_json(
    path: Path,
    *,
    download_images: bool = True,
    require_image: bool = False,
    allow_static_map_fallback: bool = True,
    skip_without_image: bool = True,
    dry_run: bool = False,
    limit: int = 0,
    offset: int = 0,
    resume_state_path: Path | None = None,
    image_delay_sec: float = 0.1,
    on_progress: Callable[[YandexImportStats, set[str]], None] | None = None,
) -> YandexImportStats:
    rows = load_facilities_json(path)
    stats = YandexImportStats()

    imported_ids: set[str] = set()
    if resume_state_path:
        imported_ids = load_import_state(resume_state_path)

    if offset > 0:
        rows = rows[offset:]
    if limit > 0:
        rows = rows[:limit]

    session = requests.Session()

    for row in rows:
        external_id = str(row.get("external_id") or "").strip()
        if resume_state_path and external_id and external_id in imported_ids:
            stats.skipped += 1
            continue

        stats.processed += 1
        try:
            if dry_run:
                kind = _normalize_kind(row.get("kind") or "")
                if kind not in {MedicalFacility.Kind.PHARMACY, MedicalFacility.Kind.HOSPITAL} or not external_id:
                    stats.skipped += 1
                    continue
                if require_image:
                    image_url, _ = resolve_facility_image_url(
                        row,
                        allow_static_map_fallback=allow_static_map_fallback,
                    )
                    if not image_url:
                        stats.skipped += 1
                        stats.skipped_no_image += 1
                        continue
                stats.created += 1
            else:
                saved = False
                with transaction.atomic():
                    saved = _upsert_facility_row(
                        row,
                        download_images=download_images,
                        require_image=require_image,
                        allow_static_map_fallback=allow_static_map_fallback,
                        image_session=session,
                        stats=stats,
                        skip_without_image=skip_without_image,
                    )
                if saved and external_id and resume_state_path:
                    imported_ids.add(external_id)
        except Exception as exc:
            stats.skipped += 1
            msg = f"{row.get('name', '?')}: {exc}"
            stats.errors.append(msg)
            logger.exception("import facility failed: %s", msg)

        if download_images and image_delay_sec > 0:
            time.sleep(image_delay_sec)

        if on_progress and stats.processed % 100 == 0:
            on_progress(stats, imported_ids)
            if resume_state_path and not dry_run:
                save_import_state(resume_state_path, imported_ids, meta={"processed": stats.processed})

    if resume_state_path and not dry_run:
        save_import_state(
            resume_state_path,
            imported_ids,
            meta={"last_file": str(path), "processed": stats.processed},
        )

    if on_progress:
        on_progress(stats, imported_ids)

    return stats
