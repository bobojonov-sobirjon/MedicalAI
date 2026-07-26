#!/usr/bin/env python3
"""Deploy related-diseases linking improvements to prod."""
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
        "apps/catalog/management/commands/link_disease_drugs.py",
        "/var/www/MedicalAI/apps/catalog/management/commands/link_disease_drugs.py",
    ),
]


def run(client, cmd, timeout=1800):
    print(f"\n>>> {cmd[:220]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
    if text:
        print(text[-5000:] if len(text) > 5000 else text)
    print(f"[exit={code}]")
    return code


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    print("CONNECTED")
    sftp = client.open_sftp()
    for rel, remote in FILES:
        sftp.put(str(ROOT / rel), remote)
        print("uploaded", rel)
    sftp.close()

    base = "cd /var/www/MedicalAI && source env/bin/activate"
    run(client, f"{base} && python manage.py link_disease_drugs", timeout=2400)
    run(
        client,
        f"{base} && python manage.py shell -c \""
        "from apps.catalog.models import Drug\n"
        "from apps.catalog.serializers import DrugSerializer\n"
        "from django.db.models import Count\n"
        "print('with', Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n__gt=0).count())\n"
        "print('without', Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n=0).count())\n"
        "d=Drug.objects.filter(name__icontains='Валвир').first()\n"
        "data=DrugSerializer(d).data if d else {}\n"
        "print('valvir_diseases', len(data.get('diseases') or []))\n"
        "print('has_related_alias', 'related_diseases' in data)\n"
        "print('sample', [x['name'] for x in (data.get('diseases') or [])[:5]])\n"
        "\"",
    )
    run(client, "systemctl restart medical; sleep 1; systemctl is-active medical")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
