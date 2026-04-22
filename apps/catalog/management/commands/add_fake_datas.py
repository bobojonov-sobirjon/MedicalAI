from __future__ import annotations

import random

from django.core.management.base import BaseCommand
from django.db import transaction

from faker import Faker

from apps.catalog.models import Disease, Drug


class Command(BaseCommand):
    help = "Add fake Diseases and Drugs (default: 100 each)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=100, help="How many diseases and drugs to create.")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for stable fake data.")

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        seed: int = options["seed"]

        random.seed(seed)
        fake = Faker("ru_RU")
        Faker.seed(seed)

        created_diseases = 0
        created_drugs = 0

        for i in range(count):
            name = f"{fake.word().capitalize()} {fake.word().capitalize()} #{seed}-{i}"
            obj, created = Disease.objects.get_or_create(
                name=name,
                defaults={"description": fake.text(max_nb_chars=240)},
            )
            if created:
                created_diseases += 1

        dosages = ["100 mg", "200 mg", "250 mg", "500 mg", "5 ml", "10 ml", "1 таб.", "2 таб."]
        all_diseases = list(Disease.objects.all())
        for i in range(count):
            name = f"{fake.word().capitalize()}-{fake.word().capitalize()} #{seed}-{i}"
            obj, created = Drug.objects.get_or_create(
                name=name,
                defaults={
                    "description": fake.text(max_nb_chars=380),
                    "dosage": random.choice(dosages),
                },
            )
            if created:
                created_drugs += 1
            # Add random "Можно лечить" diseases (0..5)
            if all_diseases:
                k = random.randint(0, min(5, len(all_diseases)))
                obj.diseases.set(random.sample(all_diseases, k=k))

        self.stdout.write(self.style.SUCCESS(f"Created diseases: {created_diseases}/{count}"))
        self.stdout.write(self.style.SUCCESS(f"Created drugs: {created_drugs}/{count}"))

