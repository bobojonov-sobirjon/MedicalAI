"""
OpenStreetMap Overpass → JSON (faqat parse, DB ga yozmaydi).

Terminal 1 (serverda, uzoq ishlaydi):
  python manage.py parse_osm_facilities --all-regions --resume

Natija: data/exports/osm_facilities.json
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.csv_import import iter_csv_rows, resolve_data_path
from apps.medic.importers.osm_overpass_parser import (
    collect_osm_facilities,
    load_regions_catalog,
    merge_facilities_from_file,
    resolve_region_row,
    save_osm_facilities_json,
)
from apps.medic.importers.yandex_parse_state import (
    filter_pending_cities,
    load_parse_state,
    mark_city_completed,
    save_parse_state,
)


class Command(BaseCommand):
    help = "Parse OSM/Overpass pharmacies and hospitals to JSON (Russia by region, resume supported)."

    def add_arguments(self, parser):
        parser.add_argument("--region", action="append", dest="regions", help="One region name (repeatable)")
        parser.add_argument("--regions-file", default="russia_regions.csv", help="Regions CSV (name, iso3166_2)")
        parser.add_argument("--all-regions", action="store_true", help="All regions from CSV")
        parser.add_argument("--limit-regions", type=int, default=0)
        parser.add_argument("--kinds", default="pharmacy,hospital")
        parser.add_argument("--delay", type=float, default=8.0, help="Pause between Overpass requests (sec)")
        parser.add_argument("--timeout", type=int, default=180, help="Overpass query timeout")
        parser.add_argument("--output", default="data/exports/osm_facilities.json")
        parser.add_argument("--resume", action="store_true", help="Skip completed regions + merge JSON")
        parser.add_argument("--state-file", default="data/cache/osm_parse_state.json")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        regions_path = resolve_data_path(options["regions_file"], base=base)
        catalog = load_regions_catalog(regions_path)
        region_rows: list[dict[str, str]] = []
        region_names = list(options.get("regions") or [])

        if region_names:
            region_rows = [resolve_region_row(name, catalog) for name in region_names if name.strip()]
        else:
            if not regions_path.exists():
                raise CommandError(f"Regions file not found: {regions_path}")
            for row in iter_csv_rows(regions_path):
                region_rows.append(resolve_region_row(row, catalog))

        state_path = base / options["state_file"]
        state = load_parse_state(state_path) if options["resume"] else {"completed_cities": [], "failed_cities": []}

        if options["resume"]:
            before = len(region_rows)
            pending_names = filter_pending_cities(
                [r.get("name") or r.get("iso3166_2") or "" for r in region_rows],
                state,
            )
            pending_set = {n.casefold() for n in pending_names}
            region_rows = [
                r
                for r in region_rows
                if (r.get("name") or r.get("iso3166_2") or "").casefold() in pending_set
            ]
            self.stdout.write(f"Resume: {before - len(region_rows)} viloyat tayyor, qolgan {len(region_rows)}")

        limit = int(options["limit_regions"] or 0)
        if limit > 0:
            region_rows = region_rows[:limit]

        if not region_rows:
            raise CommandError("Parse qilinadigan viloyat qolmadi.")

        kinds = {k.strip() for k in options["kinds"].split(",") if k.strip()}
        output_path = base / options["output"] if not Path(options["output"]).is_absolute() else Path(options["output"])

        existing_map = merge_facilities_from_file(output_path)
        if existing_map:
            self.stdout.write(f"Mavjud JSON: {len(existing_map)} ta muassasa")

        def on_region_done(region_name: str, fac_list: list, stats) -> None:
            mark_city_completed(state, region_name)
            state["facilities_total"] = len(fac_list)
            state["api_requests"] = stats.api_requests
            save_parse_state(state_path, state)
            save_osm_facilities_json(
                fac_list,
                output_path,
                meta={
                    "last_region": region_name,
                    "regions_processed": stats.regions_processed,
                    "api_requests": stats.api_requests,
                    "completed_regions": len(state.get("completed_cities", [])),
                },
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"  [{stats.regions_processed}/{len(region_rows)}] {region_name}: "
                    f"jami {len(fac_list)} (Overpass {stats.api_requests})"
                )
            )

        self.stdout.write(
            f"OSM parse boshlandi: {len(region_rows)} viloyat -> {output_path}\n"
            f"Overpass: https://overpass-api.de (bepul, kalit kerak emas)"
        )

        final_list, stats = collect_osm_facilities(
            region_rows,
            kinds=kinds,
            delay_sec=float(options["delay"]),
            existing=existing_map,
            on_region_done=on_region_done,
        )

        pharmacies = sum(1 for x in final_list if x.get("kind") == "pharmacy")
        hospitals = sum(1 for x in final_list if x.get("kind") == "hospital")

        save_osm_facilities_json(
            final_list,
            output_path,
            meta={
                "regions_processed": stats.regions_processed,
                "api_requests": stats.api_requests,
                "pharmacies": pharmacies,
                "hospitals": hospitals,
                "completed_regions": state.get("completed_cities", []),
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"TUGADI: {len(final_list)} muassasa "
                f"(apteka {pharmacies}, bolnitsa {hospitals}), Overpass ~{stats.api_requests}"
            )
        )
        self.stdout.write(f"JSON: {output_path}")
        self.stdout.write("Keyingi qadam: python manage.py import_osm_facilities --resume")
        self.stdout.write("Har bir yozuv uchun rasm majburiy (import vaqtida yuklanadi)")
        for err in stats.errors[:10]:
            self.stdout.write(self.style.WARNING(err))
