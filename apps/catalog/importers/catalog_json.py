"""JSON export/import helpers for catalog parse pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_catalog_json(
    items: list[dict[str, Any]],
    path: Path,
    *,
    entity: str,
    source: str,
    meta: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "entity": entity,
        "source": source,
        "meta": meta or {},
        "count": len(items),
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_catalog_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return raw.get("items") or raw.get("diseases") or raw.get("drugs") or []
