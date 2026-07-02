"""Resolve and download facility images (OSM tags, Wikidata, map snapshot)."""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

WIKIMEDIA_RE = re.compile(r"^File:(.+)$", re.IGNORECASE)
HTTP_IMAGE_RE = re.compile(r"^https?://", re.IGNORECASE)

OSM_IMAGE_KEYS = (
    "image",
    "image:url",
    "contact:image",
    "logo",
    "brand:logo",
    "photo",
    "panoramax",
    "mapillary",
)


def _wikimedia_file_url(value: str) -> str:
    commons = value.strip()
    if not commons:
        return ""
    match = WIKIMEDIA_RE.match(commons)
    filename = match.group(1) if match else commons
    filename = filename.replace(" ", "_")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}"


@lru_cache(maxsize=4096)
def _wikidata_commons_url(wikidata_id: str) -> str:
    qid = wikidata_id.strip().upper()
    if not qid.startswith("Q"):
        return ""

    try:
        response = requests.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
            timeout=15,
            headers={"User-Agent": "MedicAI-FacilityImporter/1.0"},
        )
        response.raise_for_status()
        entity = response.json().get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        for prop in ("P18", "P154", "P242"):
            for claim in claims.get(prop, []):
                try:
                    filename = claim["mainsnak"]["datavalue"]["value"]
                except (KeyError, TypeError):
                    continue
                if isinstance(filename, str) and filename:
                    return _wikimedia_file_url(filename)
    except requests.RequestException as exc:
        logger.debug("wikidata image lookup failed %s: %s", qid, exc)
    return ""


def yandex_static_map_url(latitude: float | Decimal, longitude: float | Decimal, *, zoom: int = 16) -> str:
    lat = float(latitude)
    lon = float(longitude)
    return (
        "https://static-maps.yandex.ru/1.x/"
        f"?ll={lon},{lat}&size=600,400&z={zoom}&l=map&pt={lon},{lat},pm2rdm"
    )


def _image_from_osm_tags(tags: dict[str, Any]) -> str:
    for key in OSM_IMAGE_KEYS:
        value = (tags.get(key) or "").strip()
        if HTTP_IMAGE_RE.match(value):
            return value
        if key in {"image", "wikimedia_commons"} and value:
            url = _wikimedia_file_url(value)
            if url:
                return url

    commons = (tags.get("wikimedia_commons") or "").strip()
    if commons:
        return _wikimedia_file_url(commons)

    mapillary = (tags.get("mapillary") or "").strip()
    if mapillary.isdigit():
        return f"https://images.mapillary.com/{mapillary}/thumb"

    return ""


def resolve_facility_image_url(
    row: dict[str, Any],
    *,
    allow_static_map_fallback: bool | None = None,
) -> tuple[str, str]:
    """
    Return (image_url, source) where source is one of:
    osm, wikidata, brand_wikidata, static_map, row.
    """
    direct = (row.get("image_url") or "").strip()
    if direct and HTTP_IMAGE_RE.match(direct):
        return direct, "row"

    images = row.get("images") or []
    if isinstance(images, list):
        for item in images:
            url = str(item or "").strip()
            if HTTP_IMAGE_RE.match(url):
                return url, "row"

    osm_tags = row.get("osm_tags") or {}
    if isinstance(osm_tags, dict):
        osm_url = _image_from_osm_tags(osm_tags)
        if osm_url:
            return osm_url, "osm"

    for field, source in (("wikidata_id", "wikidata"), ("brand_wikidata_id", "brand_wikidata")):
        qid = (row.get(field) or "").strip()
        if qid:
            url = _wikidata_commons_url(qid)
            if url:
                return url, source

    if allow_static_map_fallback is None:
        allow_static_map_fallback = bool(
            getattr(settings, "FACILITY_IMAGE_STATIC_MAP_FALLBACK", True)
        )

    lat = row.get("latitude")
    lon = row.get("longitude")
    if allow_static_map_fallback and lat is not None and lon is not None:
        try:
            return yandex_static_map_url(lat, lon), "static_map"
        except (TypeError, ValueError):
            pass

    return "", ""
