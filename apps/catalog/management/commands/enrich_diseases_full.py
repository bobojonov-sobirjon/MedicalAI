"""
Fill stub Disease rows with full spoiler sections (Wikipedia + RuTronix AI).

  python manage.py enrich_diseases_full --limit 20 --apply
  python manage.py enrich_diseases_full --limit 0 --apply --delay 0.8
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.catalog.importers.disease_full_enricher import enrich_one_disease, is_stub_disease
from apps.catalog.models import Disease
from apps.catalog.utils import clean_display_text, strip_mkb_public_text


class Command(BaseCommand):
    help = "Generate full disease descriptions/sections for MKB stubs (AI + Wikipedia)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="0 = all stubs")
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--delay", type=float, default=0.7)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--name", default="", help="Only diseases matching name")
        parser.add_argument("--no-wiki", action="store_true")
        parser.add_argument("--no-ai", action="store_true")
        parser.add_argument("--offline", action="store_true", help="No Wikipedia/AI — write fallback text for stubs")
        parser.add_argument("--min-instr", type=int, default=250)

    def handle(self, *args, **options):
        qs = Disease.objects.all().order_by("id")
        name = (options["name"] or "").strip()
        if name:
            qs = qs.filter(name__icontains=name)

        rows: list[Disease] = []
        skipped = 0
        for d in qs.iterator(chunk_size=200):
            if not is_stub_disease(
                description=d.description or "",
                instructions=getattr(d, "instructions", "") or "",
                min_instr=options["min_instr"],
            ):
                continue
            if skipped < options["offset"]:
                skipped += 1
                continue
            rows.append(d)
            if options["limit"] > 0 and len(rows) >= options["limit"]:
                break

        self.stdout.write(f"Stubs to enrich: {len(rows)}")
        ok = fail = 0
        for i, d in enumerate(rows, 1):
            result = enrich_one_disease(
                name=d.name,
                description=d.description or "",
                use_wikipedia=not options["no_wiki"] and not options["offline"],
                use_ai=not options["no_ai"] and not options["offline"],
            )
            if not result:
                fail += 1
                self.stdout.write(self.style.WARNING(f"  [{i}] FAIL {d.name[:60]}"))
            else:
                ok += 1
                if options["apply"]:
                    d.instructions = result["instructions"]
                    # Keep MKB code line if present, else set overview.
                    old = strip_mkb_public_text(d.description or "")
                    # Always store the disease's own overview, never MKB codes.
                    d.description = result["description"]
                    d.save(update_fields=["instructions", "description", "updated_at"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [{i}] OK {d.name[:50]} instr={len(result['instructions'])} src={result['source']}"
                    )
                )
            if options["delay"] > 0:
                time.sleep(options["delay"])

        self.stdout.write(self.style.SUCCESS(f"Done ok={ok} fail={fail} apply={options['apply']}"))
