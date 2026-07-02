"""Load / save Yandex parse progress (city-level resume)."""

from __future__ import annotations

import json
from pathlib import Path


def load_parse_state(path: Path) -> dict:
    if not path.exists():
        return {"completed_cities": [], "failed_cities": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed_cities": [], "failed_cities": []}


def save_parse_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def filter_pending_cities(cities: list[str], state: dict) -> list[str]:
    done = {c.casefold() for c in state.get("completed_cities", [])}
    return [c for c in cities if c.strip() and c.strip().casefold() not in done]


def mark_city_completed(state: dict, city: str) -> None:
    completed = state.setdefault("completed_cities", [])
    if city not in completed:
        completed.append(city)
    state["last_city"] = city
