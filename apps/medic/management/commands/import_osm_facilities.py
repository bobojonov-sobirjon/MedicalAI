"""
OSM JSON → DB (har bir muassasa uchun rasm majburiy).

Terminal 2 (parse tugagach):
  python manage.py import_osm_facilities --resume

Rasm manbalari (ketma-ket):
  1) OSM image / Wikimedia
  2) Wikidata (P18/P154)
  3) Yandex static xarita (koordinata bo'yicha, bepul)
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.medic.importers.facilities_json import load_facilities_json
from apps.medic.importers.yandex_facility_importer import (
    import_yandex_facilities_json,
    save_import_state,
)


class Command(BaseCommand):
    help = "Import OSM facilities into DB; image is required for every record."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="data/exports/osm_facilities.json",
            help="Parsed JSON file",
        )
        parser.add_argument("--resume", action="store_true", help="Skip already imported external_id")
        parser.add_argument(
            "--state-file",
            default="data/cache/osm_import_state.json",
        )
        parser.add_argument(
            "--no-static-map",
            action="store_true",
            help="Do not use map snapshot fallback when OSM has no photo",
        )
        parser.add_argument(
            "--require-image",
            action="store_true",
            help="Пропускать учреждения без картинки (по умолчанию импортируем ВСЕ, карту рисует клиент).",
        )
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Не скачивать картинки вообще (быстро). API отдаёт static-карту по координатам.",
        )
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--image-delay", type=float, default=0.12)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        input_path = Path(options["input"])
        if not input_path.is_absolute():
            input_path = base / input_path

        if not input_path.exists():
            raise CommandError(
                f"JSON topilmadi: {input_path}\nAvval parse_osm_facilities ishga tushiring."
            )

        total = len(load_facilities_json(input_path))
        require_image = bool(options["require_image"])
        download_images = not options["no_images"]
        self.stdout.write(
            f"Import: {input_path} ({total} yozuv), "
            + ("rasm majburiy" if require_image else "rasm ixtiyoriy — barcha yoziladi")
            + ("" if download_images else " | rasm YUKLANMAYDI (tez rejim)")
        )

        state_path = base / options["state_file"]
        allow_static = not options["no_static_map"] and bool(
            getattr(settings, "FACILITY_IMAGE_STATIC_MAP_FALLBACK", True)
        )
        if allow_static:
            self.stdout.write(
                "Rasm fallback: OSM/Wikidata yo'q bo'lsa Yandex static xarita ishlatiladi"
            )
        elif require_image:
            self.stdout.write(
                self.style.WARNING(
                    "Faqat OSM/Wikidata rasmlari — ko'p yozuvlar o'tkazib yuborilishi mumkin"
                )
            )

        def on_progress(stats, imported_ids) -> None:
            self.stdout.write(
                f"  processed={stats.processed} +{stats.created} ~{stats.updated} "
                f"skip={stats.skipped} no_image={stats.skipped_no_image} "
                f"images={stats.images_saved} err_img={stats.image_errors}"
            )
            if options["resume"] and not options["dry_run"]:
                save_import_state(state_path, imported_ids, meta={"processed": stats.processed})

        stats = import_yandex_facilities_json(
            input_path,
            download_images=download_images,
            require_image=require_image,
            allow_static_map_fallback=allow_static,
            skip_without_image=require_image,
            dry_run=options["dry_run"],
            limit=options["limit"],
            offset=options["offset"],
            resume_state_path=state_path if options["resume"] else None,
            image_delay_sec=options["image_delay"] if download_images else 0.0,
            on_progress=on_progress,
        )

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}TUGADI: processed={stats.processed} created={stats.created} "
                f"updated={stats.updated} skipped={stats.skipped} "
                f"no_image={stats.skipped_no_image} images_saved={stats.images_saved}"
            )
        )
        for err in stats.errors[:20]:
            self.stdout.write(self.style.WARNING(err))
