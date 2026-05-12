from __future__ import annotations

from django.core.files.uploadedfile import UploadedFile

from apps.catalog.models import Drug
from apps.core.gemini import GeminiConfigError, recognize_drug_name_from_image
from apps.core.rutronix import RuTronixConfigError


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


def recognize_cabinet_upload(
    image_bytes: bytes,
    mime_type: str,
    *,
    source_file: UploadedFile | None = None,
) -> dict:
    """TZ §7.14 — при отсутствии в БД создаётся новая карточка лекарства."""
    try:
        recognized = recognize_drug_name_from_image(image_bytes, mime_type)
    except (GeminiConfigError, RuTronixConfigError):
        recognized = ""
    drug, pk = match_drug_by_name(recognized)
    if drug is None and recognized and len(recognized.strip()) > 2:
        low = recognized.lower()
        if not low.startswith("не удалось"):
            name_clean = recognized.strip()[:255]
            drug = Drug.objects.filter(name__iexact=name_clean).first()
            if not drug:
                drug = Drug.objects.create(name=name_clean)
            if source_file and not drug.image:
                drug.image.save(source_file.name, source_file, save=True)
            pk = drug.id
    return {"recognized_name": recognized or "", "matched_drug": drug, "matched_drug_id": pk}
