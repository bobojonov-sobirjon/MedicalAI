from __future__ import annotations

import re

from apps.catalog.models import Disease, Drug

FAKE_NAME_RE = re.compile(r"#\d+-\d+")
FAKE_DESCRIPTION_RE = re.compile(
    r"(полностью|результат важный|цепочка|прелесть понятный|невозможно плод|темнеть хлеб)",
    re.IGNORECASE,
)


def is_fake_catalog_name(name: str) -> bool:
    label = (name or "").strip()
    if not label:
        return True
    if FAKE_NAME_RE.search(label):
        return True
    if "-" in label and label.count("-") == 1 and not label.startswith("COVID"):
        left, right = label.split("-", 1)
        if left and right and left[0].isupper() and right and right[0].isupper() and "#" in right:
            return True
    return False


def is_fake_catalog_description(description: str) -> bool:
    text = (description or "").strip()
    if not text:
        return False
    return bool(FAKE_DESCRIPTION_RE.search(text))


def iter_fake_diseases():
    for row in Disease.objects.all().only("id", "name", "description"):
        if is_fake_catalog_name(row.name) or is_fake_catalog_description(row.description):
            yield row


def iter_fake_drugs():
    for row in Drug.objects.all().only("id", "name", "description"):
        if is_fake_catalog_name(row.name) or is_fake_catalog_description(row.description):
            yield row
