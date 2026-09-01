"""Rewrite Drug/Disease texts: drop Vidal CSS/JS/ads leftover, keep Markdown sections."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog.disease_sections import build_disease_sections
from apps.catalog.instruction_sections import build_drug_sections
from apps.catalog.models import Disease, Drug
from apps.catalog.utils import flatten_display_text, is_junk_scraped_text, is_registry_meta_text


def _looks_like_page_junk(text: str) -> bool:
    raw = text or ""
    low = raw.casefold()
    return any(
        tok in low
        for tok in (
            "vidalready",
            "yacontext",
            "yandex_rtb",
            "!important",
            "queryselector",
            "flex-direction",
            "banner-comment",
            "ispartof",
        )
    )


class Command(BaseCommand):
    help = "Sanitize scraped CSS/JS out of catalog texts and rebuild spoiler Markdown."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        apply = options["apply"]
        n_drugs = n_diseases = 0

        qs = Drug.objects.all().only("id", "name", "description", "instructions", "dosage")
        if options["limit"]:
            qs = qs[: options["limit"]]
        for d in qs.iterator(chunk_size=200):
            sections = build_drug_sections(
                name=d.name or "",
                description=d.description or "",
                instructions=d.instructions or "",
                dosage=d.dosage or "",
            )
            instr = "\n\n".join(f"{row['title']}\n{row['text']}" for row in sections)[:20000]
            if not instr and _looks_like_page_junk(d.instructions or ""):
                instr = ""
            desc = flatten_display_text(d.description or "")
            if (
                is_junk_scraped_text(desc)
                or _looks_like_page_junk(d.description or "")
                or is_registry_meta_text(desc)
            ):
                desc = flatten_display_text(
                    next((s["text"] for s in sections if s["key"] in {"action", "indications", "composition"}), "")
                )
            dosage = flatten_display_text(d.dosage or "")[:255]
            if is_junk_scraped_text(dosage):
                dosage = flatten_display_text(
                    next((s["text"] for s in sections if s["key"] == "composition"), "")
                )[:255]

            fields: list[str] = []
            if instr != (d.instructions or ""):
                d.instructions = instr
                fields.append("instructions")
            if desc != (d.description or ""):
                d.description = desc[:4000]
                fields.append("description")
            if dosage != (d.dosage or ""):
                d.dosage = dosage
                fields.append("dosage")
            if fields:
                n_drugs += 1
                if apply:
                    fields.append("updated_at")
                    d.save(update_fields=fields)

        dqs = Disease.objects.all().only("id", "description", "instructions")
        if options["limit"]:
            dqs = dqs[: options["limit"]]
        for d in dqs.iterator(chunk_size=200):
            sections = build_disease_sections(
                description=d.description or "",
                instructions=getattr(d, "instructions", "") or "",
            )
            instr = "\n\n".join(f"{row['title']}\n{row['text']}" for row in sections)[:30000]
            desc = flatten_display_text(d.description or "")
            if is_junk_scraped_text(desc) or _looks_like_page_junk(d.description or ""):
                desc = flatten_display_text(
                    next((s["text"] for s in sections if s.get("key") == "overview"), "")
                )
            fields = []
            if instr != (getattr(d, "instructions", "") or ""):
                d.instructions = instr
                fields.append("instructions")
            if desc != (d.description or ""):
                d.description = desc[:4000]
                fields.append("description")
            if fields:
                n_diseases += 1
                if apply:
                    fields.append("updated_at")
                    d.save(update_fields=fields)

        self.stdout.write(
            self.style.SUCCESS(f"drugs_changed={n_drugs} diseases_changed={n_diseases} apply={apply}")
        )
