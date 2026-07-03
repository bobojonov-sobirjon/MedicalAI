"""
Vidal.ru → JSON → DB (dorilar).

Terminal 1 (uzoq, resume bilan):
  python manage.py parse_vidal_drugs --resume --fetch-details

Tez sinov (10 sahifa, detailsiz):
  python manage.py parse_vidal_drugs --limit-pages 10

Terminal 2:
  python manage.py import_parsed_catalog --drugs-only
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.importers.catalog_parsed_import import import_drugs_json
from apps.catalog.importers.vidal_drugs_parser import (
    collect_vidal_drugs,
    load_drugs_json,
    load_vidal_parse_state,
    save_drugs_json,
    save_vidal_parse_state,
)


class Command(BaseCommand):
    help = "Parse vidal.ru drug catalog to JSON (resume supported)."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="data/exports/drugs_vidal.json")
        parser.add_argument("--state-file", default="data/cache/vidal_drugs_parse_state.json")
        parser.add_argument("--resume", action="store_true")
        parser.add_argument("--fetch-details", action="store_true", help="Load description/dosage per drug")
        parser.add_argument("--limit-pages", type=int, default=0)
        parser.add_argument("--limit-details", type=int, default=0)
        parser.add_argument("--delay", type=float, default=0.6)
        parser.add_argument("--detail-delay", type=float, default=0.35)
        parser.add_argument("--import-db", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        output = base / options["output"] if not Path(options["output"]).is_absolute() else Path(options["output"])
        state_path = base / options["state_file"]

        existing: dict[str, dict] = {}
        if options["resume"] and output.exists():
            for row in load_drugs_json(output):
                eid = str(row.get("external_id") or "")
                if eid:
                    existing[f"vidal:{eid}"] = row
            self.stdout.write(f"Resume JSON: {len(existing)} dori")

        state = load_vidal_parse_state(state_path) if options["resume"] else {"completed_pages": []}
        completed = set(state.get("completed_pages", []))

        def on_page_done(page_url: str, fac_list: list, stats) -> None:
            state["completed_pages"] = sorted(set(state.get("completed_pages", [])) | {page_url})
            save_vidal_parse_state(state_path, state)
            save_drugs_json(
                fac_list,
                output,
                meta={
                    "last_page": page_url,
                    "pages_processed": stats.pages_processed,
                    "drugs_total": stats.drugs_total,
                    "details_fetched": stats.details_fetched,
                },
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"  [{stats.pages_processed}] {page_url.split('/')[-1]}: "
                    f"jami {stats.drugs_total} dori"
                )
            )

        self.stdout.write("Vidal parse boshlandi (vidal.ru)...")

        from apps.catalog.importers.vidal_drugs_parser import discover_letter_pages, _session

        session = _session()
        pages = discover_letter_pages(session)
        if options["resume"] and completed:
            pages = [p for p in pages if p not in completed]
            self.stdout.write(f"Resume: qolgan {len(pages)} sahifa")

        final, stats = collect_vidal_drugs(
            letter_pages=pages,
            fetch_details=options["fetch_details"],
            delay_sec=float(options["delay"]),
            detail_delay_sec=float(options["detail_delay"]),
            limit_pages=int(options["limit_pages"] or 0),
            limit_details=int(options["limit_details"] or 0),
            existing=existing,
            state_path=state_path if options["resume"] else None,
            on_page_done=on_page_done,
        )

        save_drugs_json(
            final,
            output,
            meta={
                "pages_processed": stats.pages_processed,
                "drugs_total": stats.drugs_total,
                "details_fetched": stats.details_fetched,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"TUGADI: {len(final)} dori -> {output} "
                f"(sahifalar {stats.pages_processed}, details {stats.details_fetched})"
            )
        )
        for err in stats.errors[:15]:
            self.stdout.write(self.style.WARNING(err))

        if options["import_db"]:
            result = import_drugs_json(output, dry_run=options["dry_run"])
            prefix = "[dry-run] " if options["dry_run"] else ""
            self.stdout.write(f"{prefix}DB: +{result.drugs_created} ~{result.drugs_updated}")
