#!/usr/bin/env python3
"""Check MedicalAI prod catalog state and apply curated Valvir + restart."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = "85.198.101.179"
USER = "root"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")


def run(client: paramiko.SSHClient, cmd: str, *, timeout: int = 600) -> tuple[int, str]:
    print(f"\n>>> {cmd[:300]}")
    _stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
    if text:
        print(text[-6000:] if len(text) > 6000 else text)
    print(f"[exit={code}]")
    return code, text


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    print("CONNECTED")

    base = "cd /var/www/MedicalAI && source env/bin/activate"

    run(
        client,
        f'{base} && python manage.py shell -c "'
        "from apps.catalog.models import Drug, Disease\n"
        "from django.db.models import Q\n"
        "print('drugs_total', Drug.objects.count())\n"
        "print('drugs_active', Drug.objects.filter(is_active=True).count())\n"
        "print('diseases', Disease.objects.count())\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values('id','name','is_active')))\n"
        "print('valtrex', list(Drug.objects.filter(name__icontains='Валтрекс').values_list('name', flat=True)[:5]))\n"
        "print('grls_desc', Drug.objects.filter(description__icontains='ГРЛС').count())\n"
        '"',
    )

    # Ensure curated enrichments exist (Валвир etc.) without full prepare_prod_data
    run(
        client,
        f"{base} && python - <<'PY'\n"
        "import os, django\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')\n"
        "django.setup()\n"
        "from apps.catalog.models import Drug\n"
        "from apps.catalog.importers.enriched_samples import DRUG_ENRICHMENTS\n"
        "created=updated=0\n"
        "for name, data in DRUG_ENRICHMENTS.items():\n"
        "    obj=Drug.objects.filter(name__iexact=name).first()\n"
        "    if obj is None:\n"
        "        Drug.objects.create(name=name, description=data.get('description',''), instructions=data.get('instructions',''), dosage=data.get('dosage',''), is_active=True)\n"
        "        created+=1\n"
        "        continue\n"
        "    ch=False\n"
        "    for field in ('description','instructions','dosage'):\n"
        "        val=data.get(field)\n"
        "        if val and getattr(obj, field) != val:\n"
        "            setattr(obj, field, val); ch=True\n"
        "    if not obj.is_active:\n"
        "        obj.is_active=True; ch=True\n"
        "    if ch:\n"
        "        obj.save(); updated+=1\n"
        "print('enrichments created', created, 'updated', updated, 'total', len(DRUG_ENRICHMENTS))\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name','is_active')))\n"
        "PY",
    )

    run(client, f"{base} && python manage.py link_disease_drugs", timeout=900)
    run(client, "systemctl restart medical; sleep 1; systemctl is-active medical")

    run(
        client,
        f'{base} && python manage.py shell -c "'
        "from apps.catalog.models import Drug\n"
        "from django.db.models import Q\n"
        "qs=Drug.objects.filter(is_active=True).filter(Q(name__icontains='Валвир')|Q(description__icontains='Валвир'))\n"
        "print('search_valvir', list(qs.values_list('name', flat=True)))\n"
        "print('active', Drug.objects.filter(is_active=True).count())\n"
        '"',
    )

    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
