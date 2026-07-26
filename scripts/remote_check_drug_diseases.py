#!/usr/bin/env python3
"""Check drug→diseases payload on prod."""
from __future__ import annotations

import os
import sys

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    cmd = r"""cd /var/www/MedicalAI && source env/bin/activate && python manage.py shell -c "
from apps.catalog.models import Drug
from apps.catalog.serializers import DrugSerializer
from django.db.models import Count
d=Drug.objects.filter(name__icontains='Валвир').first()
print('drug', getattr(d,'id',None), getattr(d,'name',None))
print('m2m', d.diseases.count() if d else 0)
if d:
  data=DrugSerializer(d).data
  print('keys', list(data.keys()))
  print('diseases_len', len(data.get('diseases') or []))
  print('sample', [(x.get('id'), x.get('name')) for x in (data.get('diseases') or [])[:5]])
print('with', Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n__gt=0).count())
print('without', Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n=0).count())
# random sample of drugs without diseases
qs=list(Drug.objects.filter(is_active=True).annotate(n=Count('diseases')).filter(n=0).order_by('?')[:8].values_list('name','description'))
for name, desc in qs:
  print('orphan', name, (desc or '')[:80])
"
"""
    _, stdout, stderr = client.exec_command(cmd, timeout=180)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("[stderr]", err[-2000:])
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
