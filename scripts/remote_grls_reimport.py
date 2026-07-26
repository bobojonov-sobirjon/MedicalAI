#!/usr/bin/env python3
"""Upload fixed GRLS importer and re-import open-data CSV on prod."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
USER = "root"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
LOCAL_IMPORTER = Path(__file__).resolve().parents[1] / "apps/catalog/importers/grls_importer.py"
REMOTE_IMPORTER = "/var/www/MedicalAI/apps/catalog/importers/grls_importer.py"


def run(client: paramiko.SSHClient, cmd: str, *, timeout: int = 1200) -> int:
    print(f"\n>>> {cmd[:220]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out[-5000:] if len(out) > 5000 else out)
    if err.strip():
        print("[stderr]", err[-1500:] if len(err) > 1500 else err)
    print(f"[exit={code}]")
    return code


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD", file=sys.stderr)
        return 2
    if not LOCAL_IMPORTER.exists():
        print(f"missing {LOCAL_IMPORTER}", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    print("CONNECTED")

    sftp = client.open_sftp()
    sftp.put(str(LOCAL_IMPORTER), REMOTE_IMPORTER)
    sftp.close()
    print("Uploaded grls_importer.py")

    base = "cd /var/www/MedicalAI && source env/bin/activate"

    run(
        client,
        f"{base} && python - <<'PY'\n"
        "import csv\n"
        "from pathlib import Path\n"
        "from collections import Counter\n"
        "p=Path('data/imports/grls_opendata.csv')\n"
        "text=p.read_text(encoding='utf-8', errors='replace')\n"
        "r=csv.DictReader(__import__('io').StringIO(text))\n"
        "n=nonempty=0\n"
        "samples=[]\n"
        "for row in r:\n"
        "    n+=1\n"
        "    t=(row.get('tradename') or '').strip()\n"
        "    if t:\n"
        "        nonempty+=1\n"
        "        if len(samples)<10: samples.append(t[:80])\n"
        "print('rows', n, 'nonempty_tradename', nonempty)\n"
        "print('samples', samples)\n"
        "PY",
    )

    run(
        client,
        f"{base} && python manage.py import_grls_drugs --file data/imports/grls_opendata.csv --apply",
        timeout=1200,
    )

    run(
        client,
        f"{base} && python manage.py link_disease_drugs",
        timeout=900,
    )

    run(
        client,
        f'{base} && python manage.py shell -c "'
        "from apps.catalog.models import Drug\n"
        "from django.db.models import Q\n"
        "print('active', Drug.objects.filter(is_active=True).count())\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name', flat=True)))\n"
        "print('sample_new', list(Drug.objects.filter(description__icontains='ГРЛС').order_by('-id').values_list('name', flat=True)[:15]))\n"
        '"',
    )

    run(client, "systemctl restart medical; systemctl is-active medical")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
