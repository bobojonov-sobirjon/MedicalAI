#!/usr/bin/env bash
# OSM JSON -> PostgreSQL + rasmlar
set -euo pipefail
cd "$(dirname "$0")/.."
python manage.py import_osm_facilities --resume "$@"
