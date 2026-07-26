#!/usr/bin/env python3
"""Remote ops for MedicalAI prod — GRLS import + curated drugs + restart."""

from __future__ import annotations

import os
import sys
import time

import paramiko

HOST = "85.198.101.179"
USER = "root"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")


def run(client: paramiko.SSHClient, cmd: str, *, timeout: int = 600) -> tuple[int, str, str]:
    print(f"\n>>> {cmd[:200]}{'...' if len(cmd) > 200 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out[-4000:] if len(out) > 4000 else out)
    if err.strip():
        print("[stderr]", err[-2000:] if len(err) > 2000 else err)
    print(f"[exit={code}]")
    return code, out, err


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD env var", file=sys.stderr)
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting...")
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    print("CONNECTED")

    base = "cd /var/www/MedicalAI && source env/bin/activate"

    run(
        client,
        f'{base} && python manage.py shell -c "from apps.catalog.models import Drug, Disease; '
        f"print('drugs', Drug.objects.count(), 'active', Drug.objects.filter(is_active=True).count()); "
        f"print('diseases', Disease.objects.count()); "
        f"print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name', flat=True)[:5])); "
        f"print('exists_grls', __import__('pathlib').Path('data/exports/drugs_vidal.json').exists())\"",
    )

    # Ensure dirs + openpyxl
    run(client, f"{base} && mkdir -p data/imports data/exports data/cache && pip install -q openpyxl==3.1.5")

    # Try download outdated but usable Minzdrav open-data GRLS CSV as bootstrap,
    # then also seed curated popular drugs including Валвир via prepare partial.
    # First: check if vidal json exists and can re-import.
    run(
        client,
        f"{base} && ls -lh data/exports/drugs_vidal.json data/exports/diseases_mkb10.json 2>/dev/null; "
        f"ls -lh data/imports/ 2>/dev/null",
    )

    # Download Minzdrav open data GRLS CSV (2017, but has many trade names)
    # Also try to fetch from alternative mirrors if any.
    download_cmd = (
        f"{base} && "
        "curl -L --fail --retry 3 --max-time 180 "
        "-A 'MedicAI-GRLS/1.0' "
        "-o data/imports/grls_opendata.csv "
        "'https://minzdrav.gov.ru/opendata/7707778246-grls/data-20170301T0000-structure-20151217T0000.csv' "
        "&& wc -l data/imports/grls_opendata.csv && head -c 500 data/imports/grls_opendata.csv"
    )
    code, out, err = run(client, download_cmd, timeout=240)

    if code != 0:
        print("OpenData download failed, trying special path...")
        run(
            client,
            f"{base} && curl -L --fail --retry 3 --max-time 180 "
            "-A 'MedicAI-GRLS/1.0' "
            "-o data/imports/grls_opendata.csv "
            "'https://minzdrav.gov.ru/special/opendata/7707778246-grls/data-20170301T0000-structure-20151217T0000.csv' "
            "&& wc -l data/imports/grls_opendata.csv",
            timeout=240,
        )

    # Inspect CSV headers
    run(client, f"{base} && python -c \"from pathlib import Path; p=Path('data/imports/grls_opendata.csv'); print(p.exists(), p.stat().st_size if p.exists() else 0); print(p.read_text(encoding='utf-8', errors='replace')[:800] if p.exists() else 'missing')\"")

    # Apply curated enrichments + Valvir without full prepare_prod_data (which cleans cities aggressively)
    run(
        client,
        f'{base} && python manage.py shell -c "'
        "from apps.catalog.importers.enriched_samples import DRUG_ENRICHMENTS, DISEASE_ENRICHMENTS\n"
        "from apps.catalog.importers.catalog_importer import _upsert_drug, _upsert_disease\n"
        "from apps.catalog.models import Drug\n"
        "created=updated=0\n"
        "for name, payload in DRUG_ENRICHMENTS.items():\n"
        "    st, obj = _upsert_drug(name, payload.get('description',''), '', dry_run=False, instructions=payload.get('instructions',''))\n"
        "    if st=='created': created+=1\n"
        "    elif st=='updated': updated+=1\n"
        "    if obj and not obj.is_active:\n"
        "        obj.is_active=True; obj.save(update_fields=['is_active','updated_at'])\n"
        "for name, desc in DISEASE_ENRICHMENTS.items():\n"
        "    _upsert_disease(name, desc, dry_run=False)\n"
        "print('curated drugs +', created, '~', updated)\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('id','name','is_active')))\n"
        '"',
        timeout=120,
    )

    # Import GRLS open data if file exists
    run(
        client,
        f"{base} && if [ -f data/imports/grls_opendata.csv ]; then "
        "python manage.py import_grls_drugs --file data/imports/grls_opendata.csv --apply; "
        "else echo 'NO_GRLS_FILE'; fi",
        timeout=900,
    )

    # Also import vidal json if present
    run(
        client,
        f"{base} && if [ -f data/exports/drugs_vidal.json ]; then "
        "python manage.py import_parsed_catalog --drugs-only; "
        "else echo 'NO_VIDAL_JSON'; fi",
        timeout=600,
    )

    # Link disease-drugs
    run(client, f"{base} && python manage.py link_disease_drugs", timeout=900)

    # Final stats
    run(
        client,
        f'{base} && python manage.py shell -c "'
        "from apps.catalog.models import Drug, Disease\n"
        "from django.db.models import Count, Q\n"
        "print('drugs_total', Drug.objects.count())\n"
        "print('drugs_active', Drug.objects.filter(is_active=True).count())\n"
        "print('diseases', Disease.objects.count())\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name','is_active')))\n"
        "print('with_diseases', Drug.objects.annotate(n=Count('diseases')).filter(n__gt=0).count())\n"
        "print('search_valvir', list(Drug.objects.filter(is_active=True).filter(Q(name__icontains='Валвир')|Q(description__icontains='Валвир')).values_list('name', flat=True)[:10]))\n"
        '"',
    )

    # Restart app
    code, out, err = run(client, "systemctl restart medical || systemctl restart medicalai || systemctl restart gunicorn || true; systemctl is-active medical medicalai gunicorn 2>/dev/null || true")
    run(client, "systemctl list-units --type=service --state=running | grep -Ei 'medical|gunicorn|daphne|uvicorn' || true")

    client.close()
    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
