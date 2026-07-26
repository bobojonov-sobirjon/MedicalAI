#!/usr/bin/env python3
"""Deploy disease name cleanup + improved disease↔drug linking to prod."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
ROOT = Path(__file__).resolve().parents[1]

FILES = [
    ("apps/catalog/utils.py", "/var/www/MedicalAI/apps/catalog/utils.py"),
    ("apps/catalog/serializers.py", "/var/www/MedicalAI/apps/catalog/serializers.py"),
    (
        "apps/catalog/importers/mkb10_parser.py",
        "/var/www/MedicalAI/apps/catalog/importers/mkb10_parser.py",
    ),
    (
        "apps/catalog/importers/disease_drug_rules.py",
        "/var/www/MedicalAI/apps/catalog/importers/disease_drug_rules.py",
    ),
    (
        "apps/catalog/management/commands/link_disease_drugs.py",
        "/var/www/MedicalAI/apps/catalog/management/commands/link_disease_drugs.py",
    ),
    (
        "apps/catalog/management/commands/cleanup_disease_names.py",
        "/var/www/MedicalAI/apps/catalog/management/commands/cleanup_disease_names.py",
    ),
]


def run(client: paramiko.SSHClient, cmd: str, *, timeout: int = 1800) -> int:
    print(f"\n>>> {cmd[:240]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
    if text:
        print(text[-6000:] if len(text) > 6000 else text)
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
    for rel, remote in FILES:
        local = ROOT / rel
        sftp.put(str(local), remote)
        print("uploaded", rel)
    sftp.close()

    base = "cd /var/www/MedicalAI && source env/bin/activate"
    run(client, f"{base} && python manage.py cleanup_disease_names", timeout=600)
    run(client, f"{base} && python manage.py link_disease_drugs", timeout=1800)
    run(
        client,
        f"{base} && python manage.py shell -c \""
        "from apps.catalog.models import Drug, Disease\n"
        "from django.db.models import Count, Q\n"
        "from apps.catalog.utils import clean_disease_display_name\n"
        "print('diseases_with_drugs', Disease.objects.annotate(n=Count('drugs')).filter(n__gt=0).count())\n"
        "print('drugs_with_diseases', Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n__gt=0).count())\n"
        "print('active_drugs', Drug.objects.filter(is_active=True).count())\n"
        "v=Drug.objects.filter(name__icontains='Валвир').first()\n"
        "print('valvir_diseases', v.diseases.count() if v else 0)\n"
        "if v:\n"
        "  names=[clean_disease_display_name(n) for n in v.diseases.values_list('name', flat=True)[:8]]\n"
        "  print('sample', names)\n"
        "eng=Disease.objects.filter(Q(name__contains='[') & Q(name__regex=r'\\[[A-Za-z]')).count()\n"
        "print('english_brackets_left', eng)\n"
        "\"",
    )
    run(client, "systemctl restart medical; sleep 1; systemctl is-active medical")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
