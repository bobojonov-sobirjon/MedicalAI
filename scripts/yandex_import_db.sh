#!/usr/bin/env bash
# Terminal 2: JSON → DB + rasmlarni yuklab saqlash
# Ishlatish: bash scripts/yandex_import_db.sh

set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONUNBUFFERED=1

JSON="${1:-data/exports/yandex_facilities.json}"

echo "=== Yandex import: DB + images ==="
echo "Fayl: $JSON"
echo "Rasmlar: media/facilities/yandex/"
echo ""

if [ ! -f "$JSON" ]; then
  echo "XATO: $JSON topilmadi. Avval yandex_parse_russia.sh ishga tushiring."
  exit 1
fi

python manage.py import_yandex_facilities \
  --input "$JSON" \
  --resume \
  --image-delay 0.08

echo ""
echo "Import tugadi."
