"""Pick readable pharmacy/hospital names from OSM tags (skip 03, +, etc.)."""

from __future__ import annotations

import re

NAME_TAG_KEYS = (
    "brand",
    "operator",
    "official_name",
    "name:ru",
    "name:en",
    "name",
    "alt_name",
)

WEAK_NAME_RE = re.compile(
    r"|".join(
        [
            r"^\s*\+\s*$",
            r"^\s*\d{1,4}\s*\+\s*$",
            r"^\s*\d{1,4}\s*$",
            r"^0{0,2}3\s*$",
            r"^аптека\s*[\d№#\s\+]*$",
            r"^аптечный\s+пункт\s*[\d№#\s\+]*$",
            r"^фарм\w*\s*[\d№#\s\+]*$",
            r"^больница\s*[\d№#\s\+]*$",
            r"^поликлиника\s*[\d№#\s\+]*$",
            r"^[\d№#\s\+]+$",
        ]
    ),
    re.IGNORECASE,
)

GENERIC_PREFIX_RE = re.compile(
    r"^(аптека|аптечный пункт|drugstore|pharmacy|больница|поликлиника)\s+",
    re.IGNORECASE,
)


AUTO_KIND_PREFIX_RE = re.compile(
    r"^(?:аптека|больница|медучреждение|аптечный пункт)\s*—\s*",
    re.IGNORECASE,
)


def clean_facility_label(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def is_weak_facility_name(name: str) -> bool:
    label = clean_facility_label(name)
    if not label:
        return True
    if len(label) <= 2:
        return True
    if WEAK_NAME_RE.match(label):
        return True
    # "21 Плюс", "03 Life" — raqam + brend, qoldiramiz
    if re.match(r"^\d{1,4}\s*\+?\s*[A-Za-zА-Яа-яЁё]", label):
        return False
    # "Аптека 5+" — faqat raqam/belgi qolgan
    stripped = GENERIC_PREFIX_RE.sub("", label).strip(" .,-№#+")
    if not stripped:
        return True
    if re.fullmatch(r"[\d№#\s\+]+", stripped):
        return True
    if len(stripped) <= 2:
        return True
    return False


def _name_score(name: str) -> int:
    label = clean_facility_label(name)
    if not label or is_weak_facility_name(label):
        return 0
    score = min(len(label), 80)
    if " " in label:
        score += 8
    if any(ch.isalpha() and ch not in "аптекаАПТЕКА" for ch in label):
        score += 12
    if re.search(r"[A-Za-zА-Яа-яЁё]{4,}", label):
        score += 10
    return score


def _combine_brand_and_branch(brand: str, branch: str) -> str:
    brand = clean_facility_label(brand)
    branch = clean_facility_label(branch)
    if not brand:
        return branch
    if not branch:
        return brand

    branch_clean = GENERIC_PREFIX_RE.sub("", branch).strip(" .,-№#+")
    if not branch_clean:
        branch_clean = branch
    if re.fullmatch(r"[\d№#\s\+]+", branch_clean):
        num = re.sub(r"\D", "", branch_clean) or branch_clean
        return f"{brand} №{num}"
    if is_weak_facility_name(branch):
        return brand
    if brand.lower() in branch.lower():
        return branch
    return f"{brand} — {branch}"


def pick_facility_name_from_osm_tags(tags: dict[str, str], *, kind: str = "") -> str:
    brand = clean_facility_label(tags.get("brand") or "")
    operator = clean_facility_label(tags.get("operator") or "")
    official = clean_facility_label(tags.get("official_name") or "")
    name_ru = clean_facility_label(tags.get("name:ru") or "")
    raw_name = clean_facility_label(tags.get("name") or tags.get("alt_name") or "")

    candidates: list[str] = []

    if brand and not is_weak_facility_name(brand):
        if raw_name and not is_weak_facility_name(raw_name):
            candidates.append(_combine_brand_and_branch(brand, raw_name))
        candidates.append(brand)

    for value in (operator, official, name_ru, raw_name):
        if value and not is_weak_facility_name(value):
            candidates.append(value)

    if brand and raw_name and is_weak_facility_name(raw_name):
        combined = _combine_brand_and_branch(brand, raw_name)
        if not is_weak_facility_name(combined):
            candidates.append(combined)

    if operator and raw_name and is_weak_facility_name(raw_name):
        combined = _combine_brand_and_branch(operator, raw_name)
        if not is_weak_facility_name(combined):
            candidates.append(combined)

    if not candidates:
        return ""

    candidates.sort(key=_name_score, reverse=True)
    return candidates[0][:255]


def build_fallback_facility_name(
    *,
    kind: str,
    city_name: str = "",
    address: str = "",
    latitude=None,
    longitude=None,
    base_name: str = "",
) -> str:
    """Manzil/shahar/koordinata — 'Аптека —' prefiksiz (ilovada xunuk ko'rinmasin)."""
    base = clean_facility_label(base_name)
    if base and not is_weak_facility_name(base):
        return base[:255]

    city = clean_facility_label(city_name)
    addr = clean_facility_label(address)

    if addr and city and city.lower() not in addr.lower():
        return f"{addr}, {city}"[:255]
    if addr:
        return addr[:255]
    if latitude is not None and longitude is not None:
        try:
            coords = f"{float(latitude):.5f}, {float(longitude):.5f}"
            if city:
                return f"{city} ({coords})"[:255]
            return coords[:255]
        except (TypeError, ValueError):
            pass
    if city:
        return city[:255]
    return ""


def cleanup_facility_display_name(name: str) -> str:
    """'Аптека — Апрель' -> 'Апрель'; prefiks faqat ortiqcha bo'lsa olib tashlanadi."""
    label = clean_facility_label(name)
    if not label:
        return ""
    stripped = AUTO_KIND_PREFIX_RE.sub("", label).strip()
    if stripped and stripped != label:
        if not is_weak_facility_name(stripped):
            return stripped[:255]
        # "Аптека — Чувашская Республика" -> "Чувашская Республика"
        if not re.match(r"^\d", stripped):
            return stripped[:255]
    return label[:255]


def pick_facility_name_from_row(row: dict, *, kind: str = "") -> str:
    kind = kind or str(row.get("kind") or "")
    osm_tags = row.get("osm_name_tags") or row.get("osm_tags") or {}
    if isinstance(osm_tags, dict) and osm_tags:
        name = pick_facility_name_from_osm_tags(osm_tags, kind=kind)
        if name:
            return cleanup_facility_display_name(name)

    for key in ("brand", "operator", "official_name", "name"):
        value = clean_facility_label(str(row.get(key) or ""))
        if value and not is_weak_facility_name(value):
            return cleanup_facility_display_name(value)

    current = clean_facility_label(str(row.get("name") or ""))
    if current and not is_weak_facility_name(current):
        return cleanup_facility_display_name(current)

    raw_for_fallback = current if current else clean_facility_label(str(row.get("name") or ""))
    fallback = build_fallback_facility_name(
        kind=kind,
        city_name=str(row.get("city_name") or row.get("city") or ""),
        address=str(row.get("address") or ""),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        base_name=raw_for_fallback,
    )
    return cleanup_facility_display_name(fallback)
