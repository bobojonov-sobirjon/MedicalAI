from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.billing.models import TariffPlan


class Command(BaseCommand):
    help = "Создать или обновить тарифы MedicAi (ТЗ §8.2.4, доп. §9.4)."

    def handle(self, *args, **options):
        trial_days = max(1, int(getattr(settings, "FREE_TRIAL_DAYS", 1)))
        plans = [
            {
                "slug": "free_trial",
                "tier": TariffPlan.Tier.FREE_TRIAL,
                "title": "Пробный период",
                "description": "Бесплатный доступ 24 часа при регистрации. Выдаётся один раз.",
                "price_rub": 0,
                "validity_days": trial_days,
                "sort_order": 0,
                "is_purchasable": False,
                "is_auto_trial": True,
                "limits": {
                    "max_disease_records": None,
                    "max_cabinet_items": None,
                    "extended_ai": True,
                    "calendar_ai": True,
                    "useful_tips": True,
                },
            },
            {
                "slug": "free",
                "tier": TariffPlan.Tier.FREE,
                "title": "Бесплатный",
                "description": "После окончания пробного периода доступен только раздел истории болезни.",
                "price_rub": 0,
                "validity_days": None,
                "sort_order": 1,
                "is_purchasable": False,
                "is_auto_trial": False,
                "limits": {
                    "max_disease_records": None,
                    "max_cabinet_items": 0,
                    "extended_ai": False,
                    "calendar_ai": False,
                    "useful_tips": False,
                },
            },
            {
                "slug": "standard",
                "tier": TariffPlan.Tier.STANDARD,
                "title": "Стандарт",
                "description": "399 ₽/мес — расширенный AI, аптечка без лимита, календарь с анализом.",
                "price_rub": 399,
                "validity_days": 30,
                "sort_order": 2,
                "is_purchasable": True,
                "is_auto_trial": False,
                "limits": {
                    "max_disease_records": None,
                    "max_cabinet_items": None,
                    "extended_ai": True,
                    "calendar_ai": True,
                    "useful_tips": True,
                    "doctor_check_discount_percent": 50,
                    "doctor_checks_discounted_per_month": 5,
                },
            },
            {
                "slug": "premium",
                "tier": TariffPlan.Tier.PREMIUM,
                "title": "Премиум",
                "description": "999 ₽/мес — всё из Стандарта + семейные профили и PDF без лимита.",
                "price_rub": 999,
                "validity_days": 30,
                "sort_order": 3,
                "is_purchasable": True,
                "is_auto_trial": False,
                "limits": {
                    "max_disease_records": None,
                    "max_cabinet_items": None,
                    "extended_ai": True,
                    "calendar_ai": True,
                    "useful_tips": True,
                    "family_profiles_max": 5,
                    "pdf_exports_per_month": None,
                    "doctor_free_checks_per_month": 3,
                },
            },
        ]
        for data in plans:
            slug = data.pop("slug")
            TariffPlan.objects.update_or_create(slug=slug, defaults=data)
        self.stdout.write(self.style.SUCCESS(f"Tariffs synced (trial_days={trial_days})."))
