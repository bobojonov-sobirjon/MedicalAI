#!/usr/bin/env python3
"""List active drugs on prod that have zero related diseases."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
OUT = Path(__file__).resolve().parents[1] / "data" / "exports" / "drugs_without_diseases.txt"


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)

    cmd = r"""cd /var/www/MedicalAI && source env/bin/activate && python manage.py shell -c "
from apps.catalog.models import Drug
from apps.catalog.utils import extract_drug_mnn
from django.db.models import Count
qs = (
    Drug.objects.filter(is_active=True)
    .annotate(n=Count('diseases'))
    .filter(n=0)
    .order_by('name')
)
total_active = Drug.objects.filter(is_active=True).count()
with_d = Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n__gt=0).count()
print('STATS', total_active, with_d, qs.count())
for d in qs.iterator(chunk_size=500):
    mnn = extract_drug_mnn(d.description or '') or '-'
    print(f'{d.id}\t{d.name}\t{mnn}')
"
"""
    _, stdout, stderr = client.exec_command(cmd, timeout=300)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    client.close()

    lines = [ln for ln in out.splitlines() if ln.startswith("STATS") or "\t" in ln]
    stats = next((ln for ln in lines if ln.startswith("STATS")), "STATS ? ? ?")
    rows = [ln for ln in lines if not ln.startswith("STATS")]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "# id\tname\tmnn\n" + "\n".join(rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )

    parts = stats.split()
    print(f"active={parts[1]} with_diseases={parts[2]} without={parts[3]}")
    print(f"saved {len(rows)} rows -> {OUT}")
    print("--- first 40 without diseases ---")
    for ln in rows[:40]:
        print(ln)
    if len(rows) > 40:
        print(f"... and {len(rows) - 40} more (see file)")
    if err.strip() and "objects imported" not in err:
        print("[stderr]", err[-1000:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
