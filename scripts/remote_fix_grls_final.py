#!/usr/bin/env python3
"""Fix GRLS on prod: upload parser, deactivate junk, re-import, link, restart."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
ROOT = Path(__file__).resolve().parents[1]
LOCAL_IMPORTER = ROOT / "apps/catalog/importers/grls_importer.py"
REMOTE_IMPORTER = "/var/www/MedicalAI/apps/catalog/importers/grls_importer.py"
REMOTE_CSV = "data/imports/grls_opendata_20160925.csv"


def run(client: paramiko.SSHClient, cmd: str, *, timeout: int = 1800) -> int:
    print(f"\n>>> {cmd[:240]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
    if text:
        print(text[-7000:] if len(text) > 7000 else text)
    print(f"[exit={code}]")
    return code


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    print("CONNECTED")

    sftp = client.open_sftp()
    sftp.put(str(LOCAL_IMPORTER), REMOTE_IMPORTER)
    sftp.close()
    print("Uploaded importer")

    base = "cd /var/www/MedicalAI && source env/bin/activate"

    # Deactivate junk from previous broken import (addresses / latin street noise)
    run(
        client,
        f"{base} && python manage.py shell -c \""
        "from apps.catalog.models import Drug\n"
        "import re\n"
        "addr=re.compile(r'(?i)street|avenue|road|str\\\\.|rue |plaza|building|house|basel|budapest|zagreb|diemen|ingelheim|freiburg')\n"
        "qs=Drug.objects.filter(description__icontains='ГРЛС', is_active=True)\n"
        "n=0\n"
        "for d in qs.iterator():\n"
        "    name=d.name or ''\n"
        "    junk=bool(addr.search(name))\n"
        "    if not junk and re.match(r'^\\\\d{2,}', name): junk=True\n"
        "    if not junk and re.search(r'[А-Яа-яЁё]', name) is None and re.search(r'\\\\d', name):\n"
        "        junk=True\n"
        "    if junk:\n"
        "        d.is_active=False\n"
        "        d.save(update_fields=['is_active'])\n"
        "        n+=1\n"
        "print('deactivated_junk', n)\n"
        "print('active', Drug.objects.filter(is_active=True).count())\n"
        "\"",
        timeout=600,
    )

    run(
        client,
        f"{base} && python manage.py import_grls_drugs --file {REMOTE_CSV}",
        timeout=600,
    )
    run(
        client,
        f"{base} && python manage.py import_grls_drugs --file {REMOTE_CSV} --apply",
        timeout=1800,
    )
    run(client, f"{base} && python manage.py cleanup_junk_drugs --apply", timeout=600)
    run(client, f"{base} && python manage.py link_disease_drugs", timeout=900)

    run(
        client,
        f"{base} && python manage.py shell -c \""
        "from apps.catalog.models import Drug\n"
        "from django.db.models import Q\n"
        "print('total', Drug.objects.count())\n"
        "print('active', Drug.objects.filter(is_active=True).count())\n"
        "print('grls_active', Drug.objects.filter(is_active=True, description__icontains='ГРЛС').count())\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name','is_active')))\n"
        "print('street_active', Drug.objects.filter(is_active=True, name__icontains='Street').count())\n"
        "\"",
    )
    run(client, "systemctl restart medical; sleep 1; systemctl is-active medical")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
