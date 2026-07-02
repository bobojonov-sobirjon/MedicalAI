#!/usr/bin/env bash
# Terminal 1: Yandex parse (butun Rossiya, uzoq ishlaydi)
# Ishlatish: bash scripts/yandex_parse_russia.sh

set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONUNBUFFERED=1

echo "=== Yandex parse: butun Rossiya ==="
echo "Kerak: .env da YANDEX_MAPS_API_KEY"
echo "Natija: data/exports/yandex_facilities.json"
echo ""

python manage.py parse_yandex_facilities \
  --all-cities \
  --cities-file cities_russia.csv \
  --resume \
  --tile-spn 0.1 \
  --max-pages 20 \
  --delay 0.35 \
  --output data/exports/yandex_facilities.json

echo ""
echo "Parse tugadi. Keyin: bash scripts/yandex_import_db.sh"
