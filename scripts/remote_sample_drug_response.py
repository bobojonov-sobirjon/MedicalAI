#!/usr/bin/env python3
"""Print sample drug detail JSON with diseases from prod."""
from __future__ import annotations

import json
import os
import sys

import paramiko

HOST = "85.198.101.179"
PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")


def main() -> int:
    if not PASSWORD:
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username="root", password=PASSWORD, timeout=30)
    cmd = r"""cd /var/www/MedicalAI && source env/bin/activate && python manage.py shell -c "
import json
from apps.catalog.models import Drug
from apps.catalog.serializers import DrugSerializer
d=Drug.objects.filter(name__icontains='Валвир', is_active=True).first()
data=DrugSerializer(d).data
# trim diseases for readability
diseases=data.get('diseases') or []
data['diseases']=diseases[:3]
data['related_diseases']=data.get('related_diseases', diseases)[:3]
data['_meta']={'diseases_total': len(diseases), 'drug_id': d.id, 'drug_name': d.name}
print(json.dumps(data, ensure_ascii=False, indent=2))
"
"""
    _, o, e = c.exec_command(cmd, timeout=120)
    print(o.read().decode("utf-8", "replace"))
    err = e.read().decode("utf-8", "replace")
    if err.strip() and "objects imported" not in err:
        print(err[-500:], file=sys.stderr)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
