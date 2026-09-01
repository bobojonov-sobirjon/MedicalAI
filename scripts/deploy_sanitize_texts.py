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
    "apps/catalog/disease_sections.py",
    "apps/catalog/serializers.py",
    "apps/catalog/importers/vidal_drugs_parser.py",
    "apps/catalog/management/commands/sanitize_catalog_texts.py",
    "apps/catalog/management/commands/enrich_drugs_from_vidal.py",
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
    "docs/FRONTEND_FAMILY_PROFILES.md",
]


def run(client, cmd: str, timeout: int = 1800) -> int:
    print(">>>", cmd[:220], flush=True)
    _i, o, e = client.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    text = (out + ("\n" + err if err.strip() else "")).strip()
    if text:
        print(text[-4000:] if len(text) > 4000 else text, flush=True)
    print("exit", code, flush=True)
    return code


def main() -> int:
    if not PASSWORD:
        print("Set MEDICALAI_SSH_PASSWORD", flush=True)
        return 2
    print("connecting...", flush=True)
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30, banner_timeout=30, auth_timeout=30)
    print("connected", flush=True)
    sftp = c.open_sftp()
    for rel in FILES:
        sftp.put(str(LOCAL / rel), f"{REMOTE}/{rel}")
        print("PUT", rel, flush=True)
    sftp.close()

    run(
        c,
        f"cd {REMOTE} && source env/bin/activate && python manage.py migrate accounts --noinput",
        timeout=120,
    )
    run(c, "systemctl restart medical || true", timeout=60)
    run(c, f"cd {REMOTE} && source env/bin/activate && python manage.py sanitize_catalog_texts --apply", timeout=1800)
    run(
        c,
        f"cd {REMOTE} && source env/bin/activate && "
        "python manage.py enrich_drugs_from_vidal --name Вазотон --apply --delay 0.35",
        timeout=400,
    )
    # Re-fetch other junk cards in background on the server.
    run(
        c,
        "bash -lc "
        "'cd /var/www/MedicalAI && source env/bin/activate && "
        "nohup python manage.py enrich_drugs_from_vidal --only-junk --limit 120 --apply --delay 0.35 "
        ">/tmp/enrich_junk.log 2>&1 & echo STARTED'",
        timeout=30,
    )
    c.close()
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
