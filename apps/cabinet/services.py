from __future__ import annotations

import re

from django.contrib.auth.models import AbstractBaseUser
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q

from apps.catalog.models import Drug
from apps.core.gemini import (
    recognize_drug_name_from_image,
    recognize_drug_names_from_image,
)

from .models import CabinetItem

_NORMALIZE_RE = re.compile(r"[^\wа-яёА-ЯЁ]+", re.UNICODE)


def _normalize_name(name: str) -> str:
    return _NORMALIZE_RE.sub(" ", (name or "").strip()).strip().casefold()


def match_drug_by_name(name: str) -> tuple[Drug | None, int | None]:
    """
    Match only existing active drugs from catalog DB.
    Does not create new Drug records.
    """
    n = (name or "").strip()
    if not n or n.lower().startswith("не удалось"):
        return None, None

    qs = Drug.objects.filter(is_active=True)

    exact = qs.filter(name__iexact=n).first()
    if exact:
        return exact, exact.id

    # «Валвир 500» → try leading token / startswith
    token = n.split()[0]
    if len(token) >= 3:
        started = qs.filter(name__istartswith=token).order_by("name")
        if started.count() == 1:
            drug = started.first()
            return drug, drug.id
        # Prefer name that starts with full recognized string
        started_full = qs.filter(name__istartswith=n[:80]).order_by("name").first()
        if started_full:
            return started_full, started_full.id

    partial = qs.filter(name__icontains=n[: min(len(n), 80)]).order_by("name").first()
    if partial:
        return partial, partial.id

    # Soft normalize: ignore punctuation differences
    needle = _normalize_name(n)
    if len(needle) >= 3:
        for drug in qs.filter(name__icontains=needle.split()[0][:40]).order_by("name")[:30]:
            if _normalize_name(drug.name) == needle or needle in _normalize_name(drug.name):
                return drug, drug.id

    return None, None


def resolve_drug_from_name(
    name: str,
    *,
    source_file: UploadedFile | None = None,
) -> dict:
    """
    Resolve recognized name against catalog only.
    Never creates orphan Drug rows — data must come from drugs DB.
    """
    recognized = (name or "").strip()
    drug, pk = match_drug_by_name(recognized)
    # Optional: attach photo to existing catalog card if empty
    if drug and source_file and not drug.image:
        source_file.seek(0)
        drug.image.save(source_file.name, source_file, save=True)
    return {
        "recognized_name": recognized,
        "matched_drug": drug,
        "matched_drug_id": pk,
    }


def recognize_cabinet_upload(
    image_bytes: bytes,
    mime_type: str,
    *,
    source_file: UploadedFile | None = None,
) -> dict:
    recognized = recognize_drug_name_from_image(image_bytes, mime_type)
    result = resolve_drug_from_name(recognized, source_file=source_file)
    if not result["recognized_name"]:
        result["recognized_name"] = recognized or ""
    return result


def recognize_cabinet_batch(
    image_bytes: bytes,
    mime_type: str,
) -> list[dict]:
    names = recognize_drug_names_from_image(image_bytes, mime_type)
    return [resolve_drug_from_name(name) for name in names]


def add_recognized_to_cabinet(
    user: AbstractBaseUser,
    *,
    drug: Drug | None,
    photo: UploadedFile | None = None,
) -> tuple[CabinetItem | None, bool]:
    """
    Add recognized catalog drug to user's cabinet.
    Returns (cabinet_item, already_in_cabinet).
    """
    if drug is None:
        return None, False

    existing = CabinetItem.objects.filter(user=user, drug=drug).first()
    if existing:
        return existing, True

    item = CabinetItem(user=user, drug=drug)
    if photo is not None:
        photo.seek(0)
        item.photo = photo
    item.save()
    return item, False


def build_recognition_result(
    user: AbstractBaseUser,
    recognition: dict,
    *,
    add_to_cabinet: bool = False,
    photo: UploadedFile | None = None,
) -> dict:
    drug = recognition.get("matched_drug")
    payload = {
        "recognized_name": recognition.get("recognized_name") or "",
        "matched_drug_id": recognition.get("matched_drug_id"),
        "matched_drug": drug,
        "added_to_cabinet": False,
        "already_in_cabinet": False,
        "cabinet_item": None,
    }
    if not add_to_cabinet or drug is None:
        return payload

    item, already = add_recognized_to_cabinet(user, drug=drug, photo=photo)
    payload["added_to_cabinet"] = item is not None and not already
    payload["already_in_cabinet"] = already
    payload["cabinet_item"] = item
    return payload
