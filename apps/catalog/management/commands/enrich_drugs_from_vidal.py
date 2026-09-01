"""
Enrich existing Drug rows from Vidal.ru detail pages (full spoiler sections).

Matches by name (icontains / exact). Fetches https://www.vidal.ru/drugs/<slug>
when slug can be resolved from search HTML.

  python manage.py enrich_drugs_from_vidal --limit 30
  python manage.py enrich_drugs_from_vidal --name Дротаверин
  python manage.py enrich_drugs_from_vidal --only-short --limit 100 --apply
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote

import requests
from django.core.management.base import BaseCommand

from apps.catalog.importers.vidal_drugs_parser import (
    VIDAL_BASE,
    USER_AGENT,
    parse_drug_detail,
)
from apps.catalog.models import Drug

SEARCH_URL = f"{VIDAL_BASE}/search?t=all&q={{q}}"
DRUG_HREF_RE = re.compile(r'href="(/drugs/([a-z0-9][a-z0-9\-]{1,120}))"', re.I)


class Command(BaseCommand):
    help = "Fill Drug.instructions/description from Vidal detail pages."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="0 = all matching drugs")
        parser.add_argument("--name", default="", help="Single drug name substring")
        parser.add_argument("--only-short", action="store_true", help="Only drugs with short/empty instructions")
        parser.add_argument("--only-junk", action="store_true", help="Only drugs whose text still has CSS/JS leftovers")
        parser.add_argument("--delay", type=float, default=0.55)
        parser.add_argument("--apply", action="store_true", help="Write to DB (default dry-run)")
        parser.add_argument("--min-instructions", type=int, default=400)
        parser.add_argument("--id", type=int, default=0, help="Single Drug.id")
        parser.add_argument("--slug", default="", help="Force Vidal slug, e.g. vasoton-l-arginine")
        parser.add_argument("--offset", type=int, default=0, help="Skip first N matching drugs")

    def handle(self, *args, **options):
        qs = Drug.objects.filter(is_active=True).order_by("name")
        name = (options["name"] or "").strip()
        if options.get("id"):
            qs = Drug.objects.filter(pk=options["id"])
        elif name:
            qs = qs.filter(name__icontains=name)

        rows: list[Drug] = []
        skipped_offset = 0
        for d in qs.iterator(chunk_size=200):
            if options["only_short"] and len((d.instructions or "").strip()) >= options["min_instructions"]:
                continue
            if options["only_junk"]:
                blob = f"{d.instructions or ''} {d.description or ''}"
                if not any(
                    tok in blob
                    for tok in (
                        "vidalReady",
                        "yaContext",
                        "yandex_rtb",
                        "!important",
                        "querySelector",
                        "flex-direction",
                        "banner-comment",
                    )
                ):
                    continue
            if skipped_offset < options["offset"]:
                skipped_offset += 1
                continue
            rows.append(d)
            if options["limit"] > 0 and len(rows) >= options["limit"]:
                break
        self.stdout.write(f"Candidates: {len(rows)} (offset={options['offset']})")

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
        updated = skipped = failed = 0

        for drug in rows:
            slug = (options.get("slug") or "").strip() or self._resolve_slug(session, drug.name)
            if not slug:
                self.stdout.write(self.style.WARNING(f"  no slug: {drug.name[:60]}"))
                failed += 1
                time.sleep(options["delay"])
                continue
            url = f"{VIDAL_BASE}/drugs/{slug}"
            try:
                html = session.get(url, timeout=35).text
            except requests.RequestException as exc:
                self.stdout.write(self.style.WARNING(f"  fetch fail {drug.name}: {exc}"))
                failed += 1
                time.sleep(options["delay"])
                continue
            detail = parse_drug_detail(html, slug=slug)
            instr = (detail.get("instructions") or "").strip()
            desc = (detail.get("description") or "").strip()
            labeled = detail.get("sections") or {}
            section_n = len(labeled) if isinstance(labeled, dict) else 0
            if (len(instr) < 80 and len(desc) < 80) or section_n < 1:
                self.stdout.write(self.style.WARNING(f"  empty detail: {drug.name} ({slug})"))
                failed += 1
                time.sleep(options["delay"])
                continue

            old_instr = drug.instructions or ""
            from apps.catalog.utils import is_junk_scraped_text

            old_junk = is_junk_scraped_text(old_instr) or any(
                tok in old_instr
                for tok in ("vidalReady", "yaContext", "!important", "yandex_rtb", "querySelector")
            )
            should_write_instr = bool(instr) and (
                old_junk or bool(options.get("slug")) or bool(options.get("id")) or len(instr) >= 80
            )

            if not options["apply"]:
                self.stdout.write(
                    f"  DRY {drug.id} {drug.name[:40]} ← {slug} instr={len(instr)} "
                    f"desc={len(desc)} sections={section_n} replace={should_write_instr or old_junk}"
                )
                skipped += 1
            else:
                fields = []
                if should_write_instr:
                    drug.instructions = instr[:20000]
                    fields.append("instructions")
                force = old_junk or bool(options.get("slug")) or bool(options.get("id"))
                if desc and (force or len(desc) > len((drug.description or "").strip())):
                    drug.description = desc[:4000]
                    fields.append("description")
                dosage = (detail.get("dosage") or "").strip()
                if dosage and (force or not (drug.dosage or "").strip()):
                    drug.dosage = dosage[:255]
                    fields.append("dosage")
                if fields:
                    fields.append("updated_at")
                    drug.save(update_fields=fields)
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f"  OK {drug.name[:50]} ({','.join(fields)})"))
                else:
                    skipped += 1
            time.sleep(options["delay"])

        self.stdout.write(
            self.style.SUCCESS(f"Done updated={updated} dry/skipped={skipped} failed={failed}")
        )

    def _resolve_slug(self, session: requests.Session, name: str) -> str | None:
        q = name.split()[0] if name else ""
        if len(q) < 3:
            q = name[:40]
        try:
            html = session.get(SEARCH_URL.format(q=quote(q)), timeout=30).text
        except requests.RequestException:
            return None
        # Prefer slug that looks like the drug name
        needle = re.sub(r"[^a-z0-9а-яё]+", "", name.casefold())
        candidates: list[str] = []
        for _href, slug in DRUG_HREF_RE.findall(html):
            low = slug.lower()
            if low in {"products", "disease", "search", "analog"}:
                continue
            candidates.append(low)
        if not candidates:
            return None
        # score
        best = None
        best_score = -1
        for slug in candidates[:40]:
            slug_norm = slug.replace("-", "")
            score = 0
            if slug_norm and slug_norm in needle:
                score += 5
            if needle and needle[:6] and needle[:6] in slug_norm:
                score += 3
            # cyrillic names won't match latin slugs well — fallback first product-like
            if score > best_score:
                best_score = score
                best = slug
        return best or candidates[0]
