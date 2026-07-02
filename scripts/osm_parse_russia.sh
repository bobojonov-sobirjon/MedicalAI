#!/usr/bin/env bash
# OSM Overpass: Rossiya viloyatlari bo'yicha apteka/shifoxona -> JSON
set -euo pipefail
cd "$(dirname "$0")/.."
python manage.py parse_osm_facilities --all-regions --resume "$@"
