"""Shared JSON format for parsed medical facilities (OSM, CSV, etc.)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_facilities_json(
    facilities: list[dict[str, Any]],
    path: Path,
    *,
    source: str = "osm",
    meta: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "meta": meta or {},
        "count": len(facilities),
        "facilities": facilities,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_facilities_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return raw.get("facilities") or raw.get("items") or []
