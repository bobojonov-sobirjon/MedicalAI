"""МКБ-10 (ICD-10) diseases parser — Russian disease names for Disease model."""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .catalog_json import load_catalog_json, save_catalog_json

logger = logging.getLogger(__name__)

DEFAULT_MKB10_CSV_URL = (
    "https://raw.githubusercontent.com/KindYAK/mkb-10-parsed/master/mkb-parsed.csv"
)
USER_AGENT = "MedicAI-MKB10-Importer/1.0 (+https://medic-ai.ru)"

RANGE_CODE_RE = re.compile(r"^[A-Z]\d{2}-[A-Z]\d{2}$")
CHAPTER_CODE_RE = re.compile(r"^[A-Z]\d{2}-[A-Z]\d{2}$|^[A-Z]{1,2}\d{0,2}-[A-Z]{1,2}\d{0,2}$")


@dataclass
class Mkb10ParseStats:
    rows_total: int = 0
    diseases_kept: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def download_mkb10_csv(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=120, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def _parse_level(raw: str) -> int:
    try:
        return int((raw or "0").strip())
    except ValueError:
        return 0


def is_importable_mkb_row(code: str, name: str, level: int) -> bool:
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not name or len(name) < 2:
        return False
    if level < 2:
        return False
    if RANGE_CODE_RE.match(code):
        return False
    if code.count("-") == 1 and len(code) <= 7 and level < 3:
        return False
    return True


def row_to_disease_item(code: str, name: str, level: int) -> dict[str, Any]:
    from apps.catalog.utils import clean_disease_display_name

    code = code.strip().upper()
    name = clean_disease_display_name(name.strip())
    description = ""  # patient text is filled later (Vidal/AI); never store MKB code as description
    return {
        "name": name[:255],
        "description": description[:2000],
        "mkb_code": code,
        "mkb_level": level,
        "external_source": "mkb10",
        "external_id": code,
    }


def parse_mkb10_csv_text(text: str, *, min_level: int = 2) -> tuple[list[dict[str, Any]], Mkb10ParseStats]:
    stats = Mkb10ParseStats()
    items: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        stats.rows_total += 1
        code = row.get("code") or row.get("МКБ") or row.get("mkb_code") or ""
        name = row.get("name") or row.get("название") or row.get("Index") or ""
        level = _parse_level(row.get("level") or row.get("уровень") or "0")
        if level < min_level:
            stats.skipped += 1
            continue
        if not is_importable_mkb_row(code, name, level):
            stats.skipped += 1
            continue
        key = name.casefold()
        if key in seen_names:
            stats.skipped += 1
            continue
        seen_names.add(key)
        items.append(row_to_disease_item(code, name, level))
        stats.diseases_kept += 1

    items.sort(key=lambda x: (x.get("mkb_code") or "", x.get("name") or ""))
    return items, stats


def parse_mkb10_csv_file(path: Path, *, min_level: int = 2) -> tuple[list[dict[str, Any]], Mkb10ParseStats]:
    text = path.read_text(encoding="utf-8-sig")
    return parse_mkb10_csv_text(text, min_level=min_level)


def fetch_and_parse_mkb10(
    *,
    csv_path: Path | None = None,
    csv_url: str = DEFAULT_MKB10_CSV_URL,
    min_level: int = 2,
    download: bool = True,
) -> tuple[list[dict[str, Any]], Mkb10ParseStats]:
    path = csv_path
    if path is None or (download and not path.exists()):
        path = path or Path("data/cache/mkb10.csv")
        if download:
            try:
                download_mkb10_csv(csv_url, path)
            except requests.RequestException as exc:
                stats = Mkb10ParseStats(errors=[f"MKB CSV yuklab bo'lmadi: {exc}"])
                return [], stats
    if not path or not path.exists():
        return [], Mkb10ParseStats(errors=[f"CSV topilmadi: {path}"])
    return parse_mkb10_csv_file(path, min_level=min_level)


def save_diseases_json(items: list[dict[str, Any]], path: Path, *, meta: dict | None = None) -> None:
    save_catalog_json(items, path, entity="disease", source="mkb10", meta=meta)


def load_diseases_json(path: Path) -> list[dict[str, Any]]:
    return load_catalog_json(path)
