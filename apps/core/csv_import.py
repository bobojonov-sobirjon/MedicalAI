"""Shared CSV helpers for TZ data import commands."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator


def resolve_data_path(path: str | Path, *, base: Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    candidate = base / p
    if candidate.exists():
        return candidate
    return base / "data" / "samples" / p.name if (base / "data" / "samples" / p.name).exists() else candidate


def iter_csv_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return
        for raw in reader:
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
            if any(row.values()):
                yield row


def split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]
