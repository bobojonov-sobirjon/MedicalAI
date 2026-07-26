#!/usr/bin/env python3
"""Deploy full disease linking so every active drug has related diseases."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/var/www/MedicalAI/apps/catalog/management/commands/link_disease_drugs.py"
LOCAL = ROOT / "apps/catalog/management/commands/link_disease_drugs.py"


def run(client, cmd, timeout=3600):
    print(f"\n>>> {cmd[:220]}")
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
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    print("CONNECTED")
    sftp = client.open_sftp()
    sftp.put(str(LOCAL), REMOTE)
    sftp.close()
    print("uploaded linker")

    base = "cd /var/www/MedicalAI && source env/bin/activate"
    run(client, f"{base} && python manage.py link_disease_drugs", timeout=3600)
    run(
        client,
        f"{base} && python manage.py shell -c \""
        "from apps.catalog.models import Drug\n"
        "from django.db.models import Count\n"
        "active=Drug.objects.filter(is_active=True)\n"
        "with_d=active.annotate(n=Count('diseases')).filter(n__gt=0).count()\n"
        "without=active.annotate(n=Count('diseases')).filter(n=0).count()\n"
        "print('active', active.count())\n"
        "print('with_diseases', with_d)\n"
        "print('without_diseases', without)\n"
        "print('coverage_pct', round(100.0*with_d/max(active.count(),1), 1))\n"
        "\"",
    )
    run(client, "systemctl restart medical; sleep 1; systemctl is-active medical")
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
