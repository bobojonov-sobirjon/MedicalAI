from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.medic.city_quality import city_has_facilities, is_osm_junk_city, latin_city_to_cyrillic
from apps.medic.models import City, MedicalFacility


class Command(BaseCommand):
    help = "Удалить мусорные/латинские города (Moskva, mikrorayon) и переименовать известные алиасы."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--relink-facilities", action="store_true", default=True)

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        renamed = 0
        deleted = 0
        relinked = 0

        for city in City.objects.all().order_by("id"):
            alias = latin_city_to_cyrillic(city.name)
            if alias:
                target = City.objects.filter(name__iexact=alias).first()
                if target and target.id != city.id:
                    if options["relink_facilities"] and not dry_run:
                        relinked += MedicalFacility.objects.filter(city_id=city.id).update(city_id=target.id)
                    if not dry_run:
                        city.delete()
                    deleted += 1
                    self.stdout.write(f"  merge {city.name} -> {alias}")
                elif not target and not dry_run:
                    city.name = alias
                    city.save(update_fields=["name"])
                    renamed += 1
                    self.stdout.write(f"  rename {city.name}")
                continue

            if not is_osm_junk_city(city):
                continue

            if city_has_facilities(city.id):
                self.stdout.write(self.style.WARNING(f"  skip (has facilities): {city.name}"))
                continue

            if not dry_run:
                city.delete()
            deleted += 1
            self.stdout.write(f"  delete junk: {city.name}")

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Города: удалено {deleted}, переименовано {renamed}, "
                f"объектов перепривязано {relinked}. Осталось: {City.objects.count()}"
            )
        )
