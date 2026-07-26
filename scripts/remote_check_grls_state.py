#!/usr/bin/env python3
"""Emergency: check/kill stuck GRLS import on prod; report drug counts."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")


def run(client, cmd, timeout=60):
    print(">>>", cmd[:200])
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    print((out or err)[-4000:])
    print("[exit=%s]" % code)
    return code


def main():
    if not PASSWORD:
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PASSWORD, timeout=30)
    run(c, "ps aux | grep -E 'import_grls|manage.py|remote_grls' | grep -v grep")
    run(
        c,
        "cd /var/www/MedicalAI && source env/bin/activate && python manage.py shell -c \""
        "from apps.catalog.models import Drug\n"
        "print('total', Drug.objects.count())\n"
        "print('active', Drug.objects.filter(is_active=True).count())\n"
        "print('grls', Drug.objects.filter(description__icontains='ГРЛС').count())\n"
        "print('junk_addr', Drug.objects.filter(name__icontains='Street').count())\n"
        "print('valvir', list(Drug.objects.filter(name__icontains='Валвир').values_list('name', flat=True)))\n"
        "\"",
    )
    run(c, "ls -la /var/www/MedicalAI/data/imports/ | head -30")
    run(c, "systemctl is-active medical")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
