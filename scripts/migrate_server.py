#!/usr/bin/env python3
"""
Migrate MedicalAI: old server backup -> new server deploy.
Usage:
  OLD_PASS=... NEW_PASS=... python scripts/migrate_server.py backup
  OLD_PASS=... NEW_PASS=... python scripts/migrate_server.py transfer
  OLD_PASS=... NEW_PASS=... python scripts/migrate_server.py setup
  OLD_PASS=... NEW_PASS=... python scripts/migrate_server.py all
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

OLD_HOST = "85.198.101.179"
NEW_HOST = "159.194.254.13"
USER = "root"
OLD_PASS = os.environ.get("OLD_PASS", "")
NEW_PASS = os.environ.get("NEW_PASS", "")
DOMAIN = "admin.medic-ai.ru"
APP_DIR = "/var/www/MedicalAI"
BACKUP_DIR = "/root/medicai_migrate_backup"
GITHUB = "https://github.com/bobojonov-sobirjon/MedicalAI.git"


def connect(host: str, password: str) -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=USER, password=password, timeout=45, banner_timeout=45, auth_timeout=45)
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 600) -> tuple[int, str]:
    print(f"\n>>> {cmd[:240]}", flush=True)
    _i, o, e = c.exec_command(f"bash -lc {cmd!r}", timeout=timeout)
    # Read with patience
    chan = o.channel
    deadline = time.time() + timeout
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    while not chan.exit_status_ready():
        if chan.recv_ready():
            out_chunks.append(chan.recv(65536).decode("utf-8", "replace"))
        if chan.recv_stderr_ready():
            err_chunks.append(chan.recv_stderr(65536).decode("utf-8", "replace"))
        if time.time() > deadline:
            break
        time.sleep(0.3)
    out_chunks.append(o.read().decode("utf-8", "replace"))
    err_chunks.append(e.read().decode("utf-8", "replace"))
    text = "".join(out_chunks + err_chunks).strip()
    code = chan.recv_exit_status() if chan.exit_status_ready() else -1
    if text:
        print(text[-5000:], flush=True)
    print(f"exit {code}", flush=True)
    return code, text


def phase_backup() -> None:
    if not OLD_PASS:
        sys.exit("OLD_PASS required")
    c = connect(OLD_HOST, OLD_PASS)
    run(c, f"rm -rf {BACKUP_DIR} && mkdir -p {BACKUP_DIR}")
    run(
        c,
        f"cd {APP_DIR} && "
        "DB_NAME=$(grep '^DB_NAME=' .env | cut -d= -f2- | tr -d '\"') && "
        "DB_USER=$(grep '^DB_USER=' .env | cut -d= -f2- | tr -d '\"') && "
        f"sudo -u postgres pg_dump -Fc -d \"$DB_NAME\" > {BACKUP_DIR}/db.dump && "
        f"cp .env {BACKUP_DIR}/.env && "
        f"tar czf {BACKUP_DIR}/media.tar.gz -C {APP_DIR} media 2>/dev/null || true && "
        f"ls -lh {BACKUP_DIR}/",
        timeout=1800,
    )
    c.close()
    print("BACKUP DONE on old server")


def phase_transfer() -> None:
    if not OLD_PASS or not NEW_PASS:
        sys.exit("OLD_PASS and NEW_PASS required")
    # Install sshpass on new, pull backup from old
    new = connect(NEW_HOST, NEW_PASS)
    run(new, "apt-get update -qq && apt-get install -y -qq sshpass openssh-client", timeout=600)
    run(
        new,
        f"rm -rf {BACKUP_DIR} && mkdir -p {BACKUP_DIR} && "
        f"sshpass -p {OLD_PASS!r} scp -o StrictHostKeyChecking=no -r "
        f"{USER}@{OLD_HOST}:{BACKUP_DIR}/* {BACKUP_DIR}/",
        timeout=3600,
    )
    run(new, f"ls -lh {BACKUP_DIR}/")
    new.close()
    print("TRANSFER DONE")


def phase_setup() -> None:
    if not NEW_PASS:
        sys.exit("NEW_PASS required")
    c = connect(NEW_HOST, NEW_PASS)

    # System packages
    run(
        c,
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
        "python3 python3-venv python3-dev python3-pip "
        "postgresql postgresql-contrib libpq-dev "
        "nginx git certbot python3-certbot-nginx "
        "build-essential pkg-config",
        timeout=1200,
    )

    # Clone / refresh app
    run(c, f"mkdir -p /var/www && rm -rf {APP_DIR}.bak && "
        f"(test -d {APP_DIR} && mv {APP_DIR} {APP_DIR}.bak || true)")
    run(c, f"git clone {GITHUB} {APP_DIR}", timeout=600)

    # Restore .env + media from backup
    run(c, f"test -f {BACKUP_DIR}/.env && cp {BACKUP_DIR}/.env {APP_DIR}/.env || echo 'NO BACKUP ENV'")
    run(
        c,
        f"cd {APP_DIR} && "
        f"sed -i 's|PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://{DOMAIN}|' .env && "
        f"grep -q '^PUBLIC_BASE_URL=' .env || echo 'PUBLIC_BASE_URL=https://{DOMAIN}' >> .env && "
        f"mkdir -p media && "
        f"test -f {BACKUP_DIR}/media.tar.gz && tar xzf {BACKUP_DIR}/media.tar.gz -C {APP_DIR} || true",
        timeout=600,
    )

    # Python venv
    run(
        c,
        f"cd {APP_DIR} && python3 -m venv env && "
        f"./env/bin/pip install -U pip wheel && "
        f"./env/bin/pip install -r requirements.txt",
        timeout=1800,
    )

    # Postgres: create DB from .env and restore
    run(
        c,
        f"cd {APP_DIR} && "
        "DB_NAME=$(grep '^DB_NAME=' .env | cut -d= -f2- | tr -d '\"') && "
        "DB_USER=$(grep '^DB_USER=' .env | cut -d= -f2- | tr -d '\"') && "
        "DB_PASS=$(grep '^DB_PASSWORD=' .env | cut -d= -f2- | tr -d '\"') && "
        "sudo -u postgres psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\" | grep -q 1 || "
        "sudo -u postgres psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';\" && "
        "sudo -u postgres psql -tc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\" | grep -q 1 || "
        "sudo -u postgres psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\" && "
        f"sudo -u postgres pg_restore -d \"$DB_NAME\" --clean --if-exists {BACKUP_DIR}/db.dump || "
        f"sudo -u postgres pg_restore -d \"$DB_NAME\" {BACKUP_DIR}/db.dump",
        timeout=1800,
    )

    # Django
    run(
        c,
        f"cd {APP_DIR} && source env/bin/activate && "
        "python manage.py migrate --noinput && "
        "python manage.py collectstatic --noinput",
        timeout=600,
    )

    # Permissions
    run(
        c,
        f"chown -R www-data:www-data {APP_DIR}/media {APP_DIR}/staticfiles && "
        f"chmod -R u+rwX,g+rwX {APP_DIR}/media && "
        f"find {APP_DIR}/media -type d -exec chmod 755 {{}} \\; && "
        f"find {APP_DIR}/media -type f -exec chmod 644 {{}} \\;",
        timeout=300,
    )

    # systemd socket + service (like old server, but with gunicorn.conf.py)
    socket_unit = """[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/run/medical.sock
SocketUser=www-data
SocketGroup=www-data
SocketMode=0660

[Install]
WantedBy=sockets.target
"""
    service_unit = f"""[Unit]
Description=gunicorn MedicalAI
Requires=medical.socket
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory={APP_DIR}
Environment=PATH={APP_DIR}/env/bin
EnvironmentFile=-{APP_DIR}/.env
ExecStart={APP_DIR}/env/bin/gunicorn -c {APP_DIR}/gunicorn.conf.py config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
    sftp = c.open_sftp()
    with sftp.file("/etc/systemd/system/medical.socket", "w") as f:
        f.write(socket_unit)
    with sftp.file("/etc/systemd/system/medical.service", "w") as f:
        f.write(service_unit)
    sftp.close()

    nginx_conf = f"""server {{
    listen 80;
    server_name {DOMAIN};

    client_max_body_size 25M;

    location /static/ {{
        alias {APP_DIR}/staticfiles/;
        expires 30d;
        access_log off;
    }}

    location /media/ {{
        alias {APP_DIR}/media/;
        expires 7d;
        access_log off;
    }}

    location / {{
        proxy_pass http://unix:/run/medical.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
    }}
}}
"""
    with c.open_sftp().file(f"/etc/nginx/sites-available/{DOMAIN}", "w") as f:
        f.write(nginx_conf)
    run(c, f"ln -sf /etc/nginx/sites-available/{DOMAIN} /etc/nginx/sites-enabled/{DOMAIN}")
    run(c, "nginx -t")
    run(
        c,
        "systemctl daemon-reload && "
        "systemctl enable medical.socket medical.service && "
        "systemctl start medical.socket && "
        "systemctl restart medical.service && "
        "systemctl reload nginx",
        timeout=120,
    )

    # SSL (only if DNS points here)
    run(
        c,
        f"certbot --nginx -d {DOMAIN} --non-interactive --agree-tos -m admin@{DOMAIN} --redirect || "
        "echo 'CERTBOT skipped (DNS not ready yet)'",
        timeout=300,
    )

    run(c, "systemctl is-active medical nginx postgresql")
    run(c, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1/api/catalog/diseases/?page=1\\&page_size=1 || true")
    c.close()
    print("SETUP DONE on new server")


def main() -> int:
    step = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if step in ("backup", "all"):
        phase_backup()
    if step in ("transfer", "all"):
        phase_transfer()
    if step in ("setup", "all"):
        phase_setup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
