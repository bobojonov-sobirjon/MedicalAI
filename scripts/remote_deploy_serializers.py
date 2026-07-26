#!/usr/bin/env python3
"""Upload catalog serializers and restart medical."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
LOCAL = Path(__file__).resolve().parents[1] / "apps/catalog/serializers.py"
REMOTE = "/var/www/MedicalAI/apps/catalog/serializers.py"


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    sftp.put(str(LOCAL), REMOTE)
    sftp.close()
    print("uploaded serializers")
    _, stdout, stderr = client.exec_command(
        "systemctl restart medical; sleep 1; systemctl is-active medical", timeout=60
    )
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err.strip():
        print(err)
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
