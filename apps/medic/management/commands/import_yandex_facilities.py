"""
Yandex JSON → DB (rasmlarni yuklab media/facilities/ ga saqlaydi).

Terminal 2 (serverda, parse tugagach):
  python manage.py import_yandex_facilities --resume

Yoki rasmsiz tezroq:
  python manage.py import_yandex_facilities --resume --no-images
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.medic.importers.yandex_facility_importer import (
    import_yandex_facilities_json,
    save_import_state,
)
from apps.medic.importers.yandex_maps_parser import load_facilities_json


class Command(BaseCommand):
    help = "Import Yandex facilities JSON into DB; download images to media/facilities/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="data/exports/yandex_facilities.json",
            help="Parsed JSON file",
        )
        parser.add_argument("--resume", action="store_true", help="Skip already imported external_id")
        parser.add_argument(
            "--state-file",
            default="data/cache/yandex_import_state.json",
        )
        parser.add_argument("--no-images", action="store_true", help="Do not download images")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--image-delay", type=float, default=0.08)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        input_path = Path(options["input"])
        if not input_path.is_absolute():
            input_path = base / input_path

        if not input_path.exists():
            raise CommandError(f"JSON topilmadi: {input_path}\nAvval parse_yandex_facilities ishga tushiring.")

        total = len(load_facilities_json(input_path))
        self.stdout.write(f"Import: {input_path} ({total} yozuv)")

        state_path = base / options["state_file"]

        def on_progress(stats, imported_ids) -> None:
            self.stdout.write(
                f"  processed={stats.processed} +{stats.created} ~{stats.updated} "
                f"skip={stats.skipped} images={stats.images_saved} err_img={stats.image_errors}"
            )
            if options["resume"] and not options["dry_run"]:
                save_import_state(state_path, imported_ids, meta={"processed": stats.processed})

        stats = import_yandex_facilities_json(
            input_path,
            download_images=not options["no_images"],
            dry_run=options["dry_run"],
            limit=options["limit"],
            offset=options["offset"],
            resume_state_path=state_path if options["resume"] else None,
            image_delay_sec=options["image_delay"] if not options["no_images"] else 0,
            on_progress=on_progress,
        )

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}TUGADI: processed={stats.processed} created={stats.created} "
                f"updated={stats.updated} skipped={stats.skipped} "
                f"images_saved={stats.images_saved}"
            )
        )
        for err in stats.errors[:20]:
            self.stdout.write(self.style.WARNING(err))
