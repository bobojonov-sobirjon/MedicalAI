#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "apps/catalog/serializers.py",
    "apps/catalog/views.py",
]


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=PASSWORD, timeout=30)
    sftp = client.open_sftp()
    for rel in FILES:
        sftp.put(str(ROOT / rel), f"/var/www/MedicalAI/{rel}")
        print("uploaded", rel)
    sftp.close()
    _, stdout, stderr = client.exec_command(
        "systemctl restart medical; sleep 2; systemctl is-active medical", timeout=60
    )
    print(stdout.read().decode())
    print(stderr.read().decode()[-500:])

    check = r"""cd /var/www/MedicalAI && source env/bin/activate && python manage.py shell -c "
from apps.catalog.models import Drug, Disease
from apps.catalog.serializers import DiseaseDetailSerializer, DrugSerializer
d=Drug.objects.filter(name__icontains='Аспирин кардио').first()
print('drug', getattr(d,'id',None), getattr(d,'name',None))
if not d:
  raise SystemExit
data=DrugSerializer(d).data
dis=data.get('diseases') or []
print('drug_diseases', len(dis))
if dis:
  print('nested_keys', sorted(dis[0].keys()))
  print('disease_has_drugs', len(dis[0].get('drugs') or []))
disease=Disease.objects.filter(id=dis[0]['id']).first()
dd=DiseaseDetailSerializer(disease).data
drugs=dd.get('drugs') or []
print('disease_drugs', len(drugs))
if drugs:
  print('drug_nested_keys', sorted(drugs[0].keys()))
  print('drug_has_diseases', len(drugs[0].get('diseases') or []))
"
"""
    _, stdout, stderr = client.exec_command(check, timeout=180)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("[stderr]", err[-1200:])
    client.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
