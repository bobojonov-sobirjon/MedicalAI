#!/usr/bin/env python3
"""Fix Komi ISO on prod, re-parse RU-KO, link Syktyvkar facilities."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

PASSWORD = os.environ.get("MEDICALAI_SSH_PASSWORD", "")
REMOTE = "/var/www/MedicalAI"
LOCAL = Path(__file__).resolve().parents[1]


def run(c, cmd: str, timeout: int = 600) -> int:
    print(">>>", cmd[:220], flush=True)
    _i, o, e = c.exec_command(cmd, timeout=timeout)
    text = (o.read() + e.read()).decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if text.strip():
        print(text[-4000:], flush=True)
    print("exit", code, flush=True)
    return code


CLEAN_PY = r"""
from apps.medic.models import City, MedicalFacility
syk = City.objects.filter(name="Сыктывкар").first()
if syk:
    n = MedicalFacility.objects.filter(city=syk).update(is_active=False)
    print("deactivated_bad_syk", n)
fake = City.objects.filter(name="Республика Коми").first()
if fake:
    qs = MedicalFacility.objects.filter(city=fake, longitude__lt=40)
    print("fake_komi_karelia_like", qs.count())
    print("deactivated_fake", qs.update(is_active=False))
"""

RELINK_PY = r"""
from decimal import Decimal
from apps.medic.models import City, MedicalFacility
city, _ = City.objects.get_or_create(
    name="Сыктывкар",
    defaults={"geo_level": "city", "sort_order": 80},
)
qs = MedicalFacility.objects.filter(
    latitude__gte=Decimal("61.55"),
    latitude__lte=Decimal("61.82"),
    longitude__gte=Decimal("50.60"),
    longitude__lte=Decimal("51.15"),
)
print("bbox_hits", qs.count())
print("relink", qs.update(city_id=city.id, is_active=True))
# also by city_name/address from this import wave
extra = MedicalFacility.objects.filter(
    is_active=True,
).filter(
    city__name__in=["Республика Коми", "Сыктывкар"]
) | MedicalFacility.objects.filter(address__icontains="Сыктывкар")
# Prefer bbox-only for safety; address-only already handled above for city Syktyvkar
print("syk_active", MedicalFacility.objects.filter(city=city, is_active=True).count())
print("sample", list(MedicalFacility.objects.filter(city=city, is_active=True).values_list("name", flat=True)[:10]))
# coords sanity
f = MedicalFacility.objects.filter(city=city, is_active=True).first()
if f:
    print("sample_coord", float(f.latitude), float(f.longitude), f.name[:80])
"""


def main() -> int:
    if not PASSWORD:
        return 2
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("85.198.101.179", username="root", password=PASSWORD, timeout=40)
    sftp = c.open_sftp()
    sftp.put(str(LOCAL / "data/samples/russia_regions.csv"), f"{REMOTE}/data/samples/russia_regions.csv")
    print("PUT russia_regions.csv", flush=True)
    with sftp.file(f"{REMOTE}/_tmp_clean_syk.py", "w") as f:
        f.write(CLEAN_PY)
    with sftp.file(f"{REMOTE}/_tmp_relink_syk.py", "w") as f:
        f.write(RELINK_PY)
    sftp.close()

    run(c, f"bash -lc 'cd {REMOTE} && source env/bin/activate && python manage.py shell < _tmp_clean_syk.py'", 120)

    code = run(
        c,
        f"bash -lc 'cd {REMOTE} && source env/bin/activate && "
        "python manage.py parse_osm_facilities "
        "--region \"Республика Коми\" "
        "--output data/exports/osm_komi_real.json "
        "--state-file data/cache/osm_komi_real_parse_state.json "
        "--delay 5 --timeout 220'",
        900,
    )
    if code != 0:
        c.close()
        return code

    run(
        c,
        f"bash -lc 'cd {REMOTE} && source env/bin/activate && "
        "python manage.py import_osm_facilities "
        "--input data/exports/osm_komi_real.json "
        "--state-file data/cache/osm_komi_real_import_state.json "
        "--no-images'",
        900,
    )

    run(c, f"bash -lc 'cd {REMOTE} && source env/bin/activate && python manage.py shell < _tmp_relink_syk.py'", 120)
    run(c, f"bash -lc 'rm -f {REMOTE}/_tmp_clean_syk.py {REMOTE}/_tmp_relink_syk.py'", 30)
    c.close()
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
