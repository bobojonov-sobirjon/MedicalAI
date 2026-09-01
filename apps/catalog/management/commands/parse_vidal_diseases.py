"""
Vidal encyclopedia → JSON → Disease.instructions / description.

  python manage.py parse_vidal_diseases --limit 20
  python manage.py parse_vidal_diseases --resume --import-db
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.importers.catalog_importer import _upsert_disease
from apps.catalog.importers.vidal_diseases_parser import (
    collect_vidal_diseases,
    load_diseases_json,
    save_diseases_json,
)


class Command(BaseCommand):
    help = "Parse Vidal.ru encyclopedia disease articles (sections for spoilers)."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="data/exports/diseases_vidal.json")
        parser.add_argument("--limit", type=int, default=0, help="Max articles (0 = all)")
        parser.add_argument("--delay", type=float, default=0.45)
        parser.add_argument("--resume", action="store_true")
        parser.add_argument("--force", action="store_true", help="Re-fetch even if already in JSON")
        parser.add_argument("--import-db", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        output = base / options["output"] if not Path(options["output"]).is_absolute() else Path(options["output"])

        existing: dict[str, dict] = {}
        if options["resume"] and output.exists():
            for row in load_diseases_json(output):
                eid = str(row.get("external_id") or "")
                if eid:
                    existing[f"vidal:{eid}"] = row
            self.stdout.write(f"Resume: {len(existing)} articles")

        collected: dict[str, dict] = dict(existing)

        def on_article(item, stats):
            eid = str(item.get("external_id") or "")
            if eid:
                collected[f"vidal:{eid}"] = item
            if stats.articles_ok % 10 == 0:
                save_diseases_json(
                    list(collected.values()),
                    output,
                    meta={"articles_ok": stats.articles_ok},
                )
                name = (item.get("name") or "")[:50]
                self.stdout.write(self.style.SUCCESS(f"  [{stats.articles_ok}] {name}"))

        items, stats = collect_vidal_diseases(
            delay_sec=options["delay"],
            limit=options["limit"],
            existing=collected,
            force=options["force"],
            on_article=on_article,
        )
        save_diseases_json(
            items,
            output,
            meta={
                "discovered": stats.pages_discovered,
                "fetched": stats.articles_fetched,
                "ok": stats.articles_ok,
                "errors": len(stats.errors),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Saved {len(items)} -> {output} (ok={stats.articles_ok}, errors={len(stats.errors)})"
            )
        )

        if options["import_db"]:
            created = updated = 0
            for row in items:
                status, _ = _upsert_disease(
                    row.get("name") or "",
                    row.get("description") or "",
                    dry_run=options["dry_run"],
                    instructions=row.get("instructions") or "",
                )
                if status == "created":
                    created += 1
                elif status == "updated":
                    updated += 1
            self.stdout.write(self.style.SUCCESS(f"DB: +{created} ~{updated}"))
