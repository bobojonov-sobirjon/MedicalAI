#!/usr/bin/env python3
import json
import os
import sys

import paramiko

PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("85.198.101.179", username="root", password=PASSWORD, timeout=30)
    cmd = (
        "curl -s 'http://127.0.0.1:8007/api/catalog/drugs/?page=1&page_size=2&letter=%D0%92' "
        "| python3 -c \"import sys,json; d=json.load(sys.stdin); "
        "print('count', d.get('count')); print('page', d.get('page'), d.get('page_size')); "
        "print('total_pages', d.get('total_pages')); print('n', len(d.get('results') or [])); "
        "r=(d.get('results') or [None])[0]; print('keys', list(r.keys()) if r else None); "
        "print('name', r.get('name') if r else None); print('diseases_count', r.get('diseases_count') if r else None)\""
    )
    _, stdout, stderr = client.exec_command(cmd, timeout=60)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print(err[-800:], file=sys.stderr)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
