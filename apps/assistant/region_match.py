"""Match catalog diseases to the selected body region (not generic «боль»)."""

from __future__ import annotations

import re
from typing import Any

# Tokens that match almost every «Боль …» disease and must never search alone.
_STOP = frozenset(
    {
        "боль",
        "боли",
        "болит",
        "болевые",
        "болевой",
        "симптом",
        "симптомы",
        "уточнения",
        "дополнительно",
        "при",
        "для",
        "или",
        "как",
        "что",
        "это",
        "the",
        "and",
    }
)

_REGION_BY_CODE = {
    "left_arm": "arm",
    "right_arm": "arm",
    "leg": "leg",
    "head": "head",
    "neck": "neck",
    "body": "torso",
}

_REGION_BY_LABEL = {
    "левая рука": "arm",
    "правая рука": "arm",
    "рука": "arm",
    "нога": "leg",
    "голова": "head",
    "шея": "neck",
    "тело": "torso",
}

# Positive stems for a region (disease name / description).
_HINTS: dict[str, tuple[str, ...]] = {
    "arm": (
        "рук",
        "плеч",
        "локт",
        "кист",
        "пальц",
        "предплеч",
        "конечн",
        "мышц",
        "сустав",
        "миалг",
        "артрит",
        "артроз",
        "плексит",
        "эпикондил",
        "туннель",
        "шейно-плечев",
        "невралг",
        "остеохондроз",
        "растяж",
        "ушиб",
        "перелом",
        "бурсит",
        "тендинит",
        "парестез",
        "онемен",
    ),
    "leg": (
        "ног",
        "колен",
        "стоп",
        "голен",
        "бедр",
        "лодыж",
        "конечн",
        "мышц",
        "сустав",
        "артрит",
        "артроз",
        "растяж",
        "ушиб",
        "перелом",
        "тромбофлеб",
        "варикоз",
        "ишиас",
        "радикулит",
        "онемен",
    ),
    "head": (
        "голов",
        "мигрен",
        "лиц",
        "зуб",
        "глаз",
        "ухо",
        "ушн",
        "нос",
        "синус",
        "челюст",
        "височн",
    ),
    "neck": (
        "шея",
        "шеи",
        "шей",
        "горл",
        "глотк",
        "миндал",
        "ларинг",
        "фаринг",
        "тонзил",
        "щитовид",
    ),
    "torso": (
        "спин",
        "поясниц",
        "груд",
        "живот",
        "желуд",
        "ребер",
        "позвоноч",
        "остеохондроз",
        "почк",
        "сердц",
    ),
}

# If the user picked a specific limb/head, drop these unless a local hint is also present.
_EXCLUDE: dict[str, tuple[str, ...]] = {
    "arm": (
        "горл",
        "глотк",
        "миндал",
        "тонзил",
        "фаринг",
        "ларинг",
        "кашел",
        "груд",
        "стенокард",
        "сердц",
        "пневмон",
        "бронх",
        "лиц",
        "зуб",
        "глаз",
        "нос",
        "ринит",
        "синусит",
        "отит",
        "живот",
        "желуд",
        "кишеч",
        "головн",
        "мигрен",
    ),
    "leg": (
        "горл",
        "груд",
        "сердц",
        "лиц",
        "зуб",
        "глаз",
        "рук",
        "плеч",
        "локт",
        "живот",
        "головн",
    ),
    "head": ("горл", "груд", "живот", "рук", "плеч", "ног", "колен"),
    "neck": ("живот", "ног", "колен", "локт", "кист"),
    "torso": ("горл", "миндал", "зуб", "глаз", "локт", "кист"),
}

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9\-]{3,}", re.UNICODE)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def regions_from_body_parts(body_parts: list[dict[str, Any]] | None, labels_text: str = "") -> set[str]:
    regions: set[str] = set()
    for row in body_parts or []:
        code = normalize(str(row.get("code") or ""))
        label = normalize(str(row.get("label") or ""))
        if code in _REGION_BY_CODE:
            regions.add(_REGION_BY_CODE[code])
        if label in _REGION_BY_LABEL:
            regions.add(_REGION_BY_LABEL[label])
    blob = normalize(labels_text)
    for label, region in _REGION_BY_LABEL.items():
        if label in blob:
            regions.add(region)
    return regions


def distinctive_terms(*texts: str) -> list[str]:
    """Search terms: full phrases + tokens, without generic «боль»."""
    blob = normalize("\n".join(t for t in texts if t))
    if not blob:
        return []
    phrases: list[str] = []
    for raw in re.split(r"[\n,;]+", blob):
        phrase = raw.strip(" .")
        if len(phrase) < 4:
            continue
        words = [w for w in _WORD_RE.findall(phrase) if w not in _STOP]
        if words:
            joined = " ".join(words)
            if len(joined) >= 4:
                phrases.append(joined)
            for w in words:
                if w not in _STOP and len(w) >= 4:
                    phrases.append(w)
    # de-dupe, longer first
    seen: set[str] = set()
    out: list[str] = []
    for item in sorted(set(phrases), key=len, reverse=True):
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out[:24]


def _haystack(name: str, description: str = "") -> str:
    return normalize(f"{name} {description[:400]}")


def region_score(name: str, description: str, regions: set[str], terms: list[str]) -> int | None:
    """
    None = drop (wrong region).
    Else higher is better.
    """
    hay = _haystack(name, description)
    score = 0
    for term in terms:
        if term in hay:
            score += 8 if " " in term else 3

    if regions:
        hinted = False
        excluded = False
        for region in regions:
            if any(h in hay for h in _HINTS.get(region, ())):
                hinted = True
                score += 6
            if any(x in hay for x in _EXCLUDE.get(region, ())):
                excluded = True
        if excluded and not hinted:
            return None
        if hinted:
            score += 4
        elif score == 0:
            # No overlap with selected region and no term hit — skip.
            return None

    return score


def region_name_hints(regions: set[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for region in regions:
        for hint in _HINTS.get(region, ()):
            if hint in seen or len(hint) < 4:
                continue
            seen.add(hint)
            out.append(hint)
    return out[:16]


def filter_condition_names(names: list[str], *, regions: set[str], terms: list[str]) -> list[str]:
    kept: list[str] = []
    for name in names:
        raw = (name or "").strip()
        if not raw:
            continue
        sc = region_score(raw, "", regions, terms)
        if sc is None:
            continue
        kept.append(raw)
    return kept
