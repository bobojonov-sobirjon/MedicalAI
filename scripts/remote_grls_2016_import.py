#!/usr/bin/env python3
"""Download usable GRLS open-data (2016 — has tradenames) and import on prod."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko
import urllib.request

HOST = "85.198.101.179"
USER = "root"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
LOCAL_CSV = Path(__file__).resolve().parents[1] / "data/imports/grls_opendata_20160925.csv"
REMOTE_CSV = "/var/www/MedicalAI/data/imports/grls_opendata_20160925.csv"
LOCAL_IMPORTER = Path(__file__).resolve().parents[1] / "apps/catalog/importers/grls_importer.py"
REMOTE_IMPORTER = "/var/www/MedicalAI/apps/catalog/importers/grls_importer.py"
SOURCE_URL = (
    "https://minzdrav.gov.ru/opendata/7707778246-grls/"
    "data-20160925T0000-structure-20151217T0000.csv"
)


def download() -> None:
    LOCAL_CSV.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_CSV.exists() and LOCAL_CSV.stat().st_size > 1_000_000:
        print("CSV already present", LOCAL_CSV, LOCAL_CSV.stat().st_size)
        return
    print("Downloading", SOURCE_URL)
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "MedicAI/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    LOCAL_CSV.write_bytes(data)
    print("Saved", LOCAL_CSV, len(data))


def run(client: paramiko.SSHClient, cmd: str, *, timeout: int = 1800) -> int:
    print(f"\n>>> {cmd[:250]}")
    _stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
    if text:
        print(text[-8000:] if len(text) > 8000 else text)
    print(f"[exit={code}]")
    return code


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD", file=sys.stderr)
        return 2

    download()

    # Quick local sanity
    import csv
    import io

    text = LOCAL_CSV.read_text(encoding="utf-8", errors="replace")
    r = csv.DictReader(io.StringIO(text))
    n = nonempty = 0
    samples = []
    for row in r:
        n += 1
        t = (row.get("tradename") or "").strip()
        if t:
            nonempty += 1
            if len(samples) < 8:
                samples.append(t)
    print("local rows", n, "nonempty_tradename", nonempty, "samples", samples)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    print("CONNECTED")

    sftp = client.open_sftp()
    print("Uploading importer...")
    sftp.put(str(LOCAL_IMPORTER), REMOTE_IMPORTER)
    print("Uploading CSV...", LOCAL_CSV.stat().st_size)
    sftp.put(str(LOCAL_CSV), REMOTE_CSV)
    sftp.close()
    print("Upload done")

    base = "cd /var/www/MedicalAI && source env/bin/activate"

    run(
        client,
        f"{base} && python manage.py import_grls_drugs --file data/imports/grls_opendata_20160925.csv",
        timeout=600,
    )
    run(
        client,
        f"{base} && python manage.py import_grls_drugs --file data/imports/grls_opendata_20160925.csv --apply",
        timeout=1800,
    )
    run(client, f"{base} && python manage.py link_disease_drugs", timeout=900)

    run(
        client,
        f'{base} && python manage.py shell -c "'
        "from apps.catalog.models import Drug\n"
        "from django.db.models import Q\n"
        "print('total', Drug.objects.count())\n"
        "print('active', Drug.objects.filter(is_active=True).count())\n"
        "print('grls', Drug.objects.filter(description__icontains='ГРЛС').count())\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name', flat=True)))\n"
        "print('sample', list(Drug.objects.filter(description__icontains='ГРЛС').order_by('name').values_list('name', flat=True)[:20]))\n"
        '"',
    )
    run(client, "systemctl restart medical; sleep 1; systemctl is-active medical")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
