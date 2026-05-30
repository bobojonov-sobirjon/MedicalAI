from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Q

from apps.catalog.models import Drug
from apps.core.gemini import (
    GeminiConfigError,
    recognize_drug_name_from_image,
    recognize_drug_names_from_image,
)
from apps.core.rutronix import RuTronixConfigError

from .models import CabinetItem


class CabinetRecognitionError(RuntimeError):
    """Raised when AI provider is not configured or recognition fails."""


def match_drug_by_name(name: str) -> tuple[Drug | None, int | None]:
    n = (name or "").strip()
    if not n or n.lower().startswith("не удалось"):
        return None, None
    exact = Drug.objects.filter(name__iexact=n).first()
    if exact:
        return exact, exact.id
    partial = Drug.objects.filter(name__icontains=n[: min(len(n), 80)]).order_by("name").first()
    if partial:
        return partial, partial.id
    return None, None


def resolve_drug_from_name(
    name: str,
    *,
    source_file: UploadedFile | None = None,
) -> dict:
    """Match catalog drug or create a new Drug card (TZ §7.14)."""
    recognized = (name or "").strip()
    drug, pk = match_drug_by_name(recognized)
    if drug is None and recognized and len(recognized) > 2 and not recognized.lower().startswith("не удалось"):
        name_clean = recognized[:255]
        drug = Drug.objects.filter(name__iexact=name_clean).first()
        if not drug:
            drug = Drug.objects.create(name=name_clean)
        if source_file and not drug.image:
            source_file.seek(0)
            drug.image.save(source_file.name, source_file, save=True)
        pk = drug.id
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
    Add recognized drug to user's cabinet.
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
