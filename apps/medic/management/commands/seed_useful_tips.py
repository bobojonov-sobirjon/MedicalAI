from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.medic.models import UsefulTip

SAMPLE_TIPS = [
    {
        "title": "На сколько часто нужно мыть руки?",
        "body": (
            "Мойте руки с мылом не менее 20 секунд: перед едой, после улицы, "
            "туалета и контакта с больными. Это простой способ снизить риск ОРВИ и кишечных инфекций."
        ),
        "sort_order": 10,
    },
    {
        "title": "Сколько воды пить в день?",
        "body": (
            "Ориентир для взрослых — около 1,5–2 литров жидкости в сутки, если нет ограничений врача. "
            "В жару и при нагрузке потребность выше."
        ),
        "sort_order": 20,
    },
    {
        "title": "Когда измерять давление?",
        "body": (
            "Измеряйте давление в спокойном состоянии, сидя, после 5 минут отдыха. "
            "Два измерения утром и вечером дают более точную картину, чем разовое."
        ),
        "sort_order": 30,
    },
]


class Command(BaseCommand):
    help = "Seed sample useful tips for home banner (ТЗ §7.6)."

    def handle(self, *args, **options):
        created = 0
        for row in SAMPLE_TIPS:
            obj, was_created = UsefulTip.objects.get_or_create(
                title=row["title"],
                defaults={
                    "body": row["body"],
                    "sort_order": row["sort_order"],
                    "is_active": True,
                    "show_on_home": True,
                },
            )
            if was_created:
                created += 1
            else:
                obj.body = row["body"]
                obj.show_on_home = True
                obj.is_active = True
                obj.sort_order = row["sort_order"]
                obj.save(update_fields=["body", "show_on_home", "is_active", "sort_order", "updated_at"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Useful tips: +{created} new, total home={UsefulTip.objects.filter(show_on_home=True, is_active=True).count()}"
            )
        )
