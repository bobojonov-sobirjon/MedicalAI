#!/usr/bin/env python3
"""Deploy drug list pagination to prod."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ("apps/catalog/views.py", "/var/www/MedicalAI/apps/catalog/views.py"),
    ("apps/catalog/serializers.py", "/var/www/MedicalAI/apps/catalog/serializers.py"),
]


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel, remote in FILES:
        sftp.put(str(ROOT / rel), remote)
        print("uploaded", rel)
    sftp.close()
    cmd = (
        "cd /var/www/MedicalAI && source env/bin/activate && "
        "python -c \"import django; django.setup()\" 2>/dev/null; "
        "systemctl restart medical; sleep 1; systemctl is-active medical; "
        "curl -s 'http://127.0.0.1:8007/api/catalog/drugs/?page=1&page_size=2' | head -c 800"
    )
    # Django setup needs DJANGO_SETTINGS - use manage.py shell instead
    cmd = r"""cd /var/www/MedicalAI && source env/bin/activate && systemctl restart medical && sleep 2 && systemctl is-active medical && python manage.py shell -c "
from django.test import RequestFactory
from apps.catalog.views import PublicDrugListView
rf=RequestFactory()
req=rf.get('/api/catalog/drugs/', {'page':'1','page_size':'2','q':'вал'})
req.user=type('U',(),{'is_authenticated':False})()
resp=PublicDrugListView().get(req)
print('status', resp.status_code)
print('count', resp.data.get('count'))
print('page', resp.data.get('page'), 'page_size', resp.data.get('page_size'))
print('results_len', len(resp.data.get('results') or []))
print('keys', list((resp.data.get('results') or [{}])[0].keys()) if resp.data.get('results') else [])
"
"""
    _, stdout, stderr = client.exec_command(cmd, timeout=120)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("[stderr]", err[-1500:])
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
