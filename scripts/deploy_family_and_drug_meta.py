#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
USER = "root"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
REMOTE = "/var/www/MedicalAI"
LOCAL = Path(__file__).resolve().parents[1]
FILES = [
    "apps/catalog/utils.py",
    "apps/catalog/instruction_sections.py",
    "apps/catalog/serializers.py",
    "apps/accounts/models.py",
    "apps/accounts/serializers.py",
    "apps/accounts/family_serializers.py",
    "apps/accounts/family_access.py",
    "apps/accounts/profile_views.py",
    "apps/accounts/urls.py",
    "apps/accounts/migrations/0008_customuser_active_profile_id.py",
    "apps/assistant/services.py",
    "apps/assistant/views.py",
    "docs/FRONTEND.md",
]


def run(client, cmd, timeout=90):
    print(">>>", cmd[:200], flush=True)
    _i, o, e = client.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    text = (out + ("\n" + err if err.strip() else "")).strip()
    if text:
        print(text[-3000:], flush=True)
    code = o.channel.recv_exit_status()
    print("exit", code, flush=True)
    return code


def main() -> int:
    if not PASSWORD:
        print("MEDICALAI_SSH_PASSWORD missing", file=sys.stderr)
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=40)
    sftp = c.open_sftp()
    for rel in FILES:
        remote = f"{REMOTE}/{rel}"
        sftp.put(str(LOCAL / rel), remote)
        print("PUT", rel, flush=True)
    sftp.close()
    run(
        c,
        "bash -lc 'cd /var/www/MedicalAI && source env/bin/activate && python manage.py migrate accounts --noinput'",
        timeout=90,
    )
    run(c, "systemctl restart medical", timeout=40)
    c.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
