"""
Clean disease texts (\\t, &ndash;) and copy Vidal instructions onto matching MKB rows.

  python manage.py fix_disease_texts --apply
  python manage.py fix_disease_texts --apply --hide-junk
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.catalog.models import Disease
from apps.catalog.utils import clean_display_text

JUNK_NAME_RE = re.compile(
    r"(?i)^("
    r"\d+\s+факт|"
    r"витамины\s*:|"
    r"как сохранить|"
    r"методы самоконтроля|"
    r"питание при|"
    r"альтернативные методы|"
    r"биофлавоноиды|"
    r"аминокислоты|"
    r"ферменты|"
    r"лекарственные растения"
    r")"
)

MKB_STUB_RE = re.compile(r"(?i)^МКБ-10:\s*\S+")


def _is_mkb_stub(text: str) -> bool:
    raw = clean_display_text(text or "")
    if len(raw) < 120 and MKB_STUB_RE.match(raw):
        return True
    if "Код диагноза по Международной классификации" in raw and len(raw) < 160:
        return True
    return False


def _core_tokens(name: str) -> str:
    raw = clean_display_text(name or "").casefold()
    raw = re.sub(r"\([^)]*\)", " ", raw)
    raw = re.sub(r"[^a-zа-яё0-9\s\-]+", " ", raw, flags=re.I)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


class Command(BaseCommand):
    help = "Clean \\t in disease texts; propagate Vidal instructions to MKB stubs; hide junk articles."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--hide-junk", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        apply = options["apply"]
        cleaned = linked = hidden = unlinked = 0

        qs = Disease.objects.all().order_by("id")
        if options["limit"] > 0:
            qs = qs[: options["limit"]]

        for d in qs.iterator(chunk_size=200):
            fields: list[str] = []
            old_desc = d.description or ""
            old_instr = getattr(d, "instructions", "") or ""
            new_desc = clean_display_text(old_desc)
            new_instr = clean_display_text(old_instr)
            if new_desc != old_desc:
                d.description = new_desc
                fields.append("description")
            if new_instr != old_instr:
                d.instructions = new_instr
                fields.append("instructions")
            if fields:
                cleaned += 1
                if apply:
                    fields.append("updated_at")
                    d.save(update_fields=fields)

        # Replace MKB-only descriptions with real overview from instructions.
        from apps.catalog.utils import disease_card_text, strip_mkb_public_text

        mkb_qs = Disease.objects.filter(description__icontains="МКБ-10")
        for d in mkb_qs.iterator(chunk_size=300):
            card = disease_card_text(d)
            new_desc = strip_mkb_public_text(card) if card else ""
            if not new_desc:
                new_desc = ""  # never show MKB code to patients
            if new_desc != (d.description or ""):
                cleaned += 1
                if apply:
                    d.description = new_desc
                    d.save(update_fields=["description", "updated_at"])

        # Unlink copies where one article was pasted onto a different disease
        # (e.g. all «Абсцесс …» received Бартолиновой text).
        unlinked = 0
        from collections import defaultdict

        by_instr: dict[str, list[Disease]] = defaultdict(list)
        for d in (
            Disease.objects.exclude(instructions="")
            .only("id", "name", "description", "instructions")
            .iterator(chunk_size=300)
        ):
            key = (d.instructions or "")[:800]
            if len(key) < 200:
                continue
            by_instr[key].append(d)

        for _key, group in by_instr.items():
            if len(group) < 2:
                continue
            instr_l = (group[0].instructions or "").casefold()

            def _score(item: Disease) -> int:
                toks = [t for t in _core_tokens(item.name).split() if len(t) > 3]
                return sum(1 for t in toks if t in instr_l)

            ranked = sorted(group, key=_score, reverse=True)
            winner = ranked[0]
            for d in ranked[1:]:
                if _score(d) >= max(2, _score(winner)):
                    continue
                unlinked += 1
                if apply:
                    d.instructions = ""
                    d.description = ""
                    d.save(update_fields=["instructions", "description", "updated_at"])

        # Build index of rich Vidal-like articles
        rich = list(
            Disease.objects.exclude(instructions="")
            .extra(where=["LENGTH(instructions) >= %s"], params=[400])
            .only("id", "name", "description", "instructions")
        )
        rich_by_token: dict[str, Disease] = {}
        for src in rich:
            token = _core_tokens(src.name)
            if len(token) < 4:
                continue
            rich_by_token[token] = src

        stubs = Disease.objects.filter(Q(instructions="") | Q(instructions__isnull=True)).iterator(
            chunk_size=300
        )
        for d in stubs:
            if not _is_mkb_stub(d.description or "") and len(clean_display_text(d.description or "")) > 200:
                continue
            token = _core_tokens(d.name)
            if len(token) < 4:
                continue
            src = rich_by_token.get(token)
            if not src or src.id == d.id:
                continue
            # Only copy when names are essentially the same (not just first word «абсцесс»).
            src_tok = _core_tokens(src.name)
            if src_tok != token and token not in src_tok and src_tok not in token:
                continue
            linked += 1
            if apply:
                d.instructions = src.instructions
                # Prefer rich overview as description when stub
                if _is_mkb_stub(d.description or "") and src.description:
                    d.description = clean_display_text(src.description)[:4000]
                d.save(update_fields=["instructions", "description", "updated_at"])

        if options["hide_junk"]:
            # No is_active on Disease — delete or empty? Prefer prefix rename hide via empty?
            # Soft-hide: clear from search by prefixing? Better: delete junk without drug links
            junk = Disease.objects.filter(name__regex=r"(?i)^(\d+\s+факт|витамины\s*:)")
            for d in junk.iterator():
                if d.drugs.exists():
                    continue
                hidden += 1
                if apply:
                    d.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"cleaned={cleaned} unlinked={unlinked} linked={linked} hidden_junk={hidden} apply={apply}"
            )
        )
