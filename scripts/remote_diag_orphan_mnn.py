#!/usr/bin/env python3
"""Diagnose why many drugs still lack related diseases."""
from __future__ import annotations

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
from apps.catalog.models import Drug
from apps.catalog.utils import extract_drug_mnn, split_mnn_parts
from django.db.models import Count
active=Drug.objects.filter(is_active=True)
with_d=active.annotate(n=Count('diseases')).filter(n__gt=0)
without=active.annotate(n=Count('diseases')).filter(n=0)
print('active', active.count(), 'with', with_d.count(), 'without', without.count())
has_mnn=no_mnn=0
for d in without.iterator():
  m=extract_drug_mnn(d.description or '')
  if m: has_mnn+=1
  else: no_mnn+=1
print('orphans_with_mnn', has_mnn, 'orphans_no_mnn', no_mnn)
# sample mnns of orphans
from collections import Counter
c=Counter()
for d in without.iterator():
  for p in split_mnn_parts(extract_drug_mnn(d.description or '')):
    c[p]+=1
print('top_orphan_mnn', c.most_common(15))
# how many of those top mnns exist on linked drugs?
linked_parts=set()
for d in with_d.iterator():
  for p in split_mnn_parts(extract_drug_mnn(d.description or '')):
    linked_parts.add(p)
overlap=sum(1 for p,_ in c.most_common(50) if p in linked_parts)
print('top50_overlap_with_linked', overlap)
"
"""
    _, o, e = c.exec_command(cmd, timeout=300)
    print(o.read().decode("utf-8", "replace"))
    err = e.read().decode("utf-8", "replace")
    if err.strip():
        print("[stderr]", err[-1500:])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
