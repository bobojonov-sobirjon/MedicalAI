from __future__ import annotations

import random

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Disease
from apps.medic.models import UsefulTip

# Реалистичные советы для баннера на главной (ТЗ §7.6) — не «фейкер-мусор».
CURATED_TIPS: list[tuple[str, str]] = [
    (
        "На сколько часто нужно мыть руки?",
        "Мойте руки с мылом не менее 20 секунд: перед едой, после улицы, туалета и контакта с больными.",
    ),
    (
        "Сколько воды пить в день?",
        "Ориентир для взрослых — около 1,5–2 литров жидкости в сутки, если нет ограничений врача.",
    ),
    (
        "Когда измерять давление?",
        "Измеряйте давление в спокойном состоянии, сидя, после 5 минут отдыха — утром и вечером.",
    ),
    (
        "Как правильно принимать антибиотики?",
        "Только по назначению врача, полным курсом. Не прерывайте приём при улучшении самочувствия.",
    ),
    (
        "Что делать при температуре?",
        "Пейте больше жидкости, отдыхайте. Жаропонижающие — при температуре выше 38–38,5 °C или сильном недомогании.",
    ),
    (
        "Как снизить риск ОРВИ?",
        "Проветривайте помещение, мойте руки, избегайте скоплений людей в сезон простуд, высыпайтесь.",
    ),
    (
        "Полезен ли сон для иммунитета?",
        "Да: 7–9 часов сна помогают восстановлению. Хронический недосып повышает риск инфекций.",
    ),
    (
        "Когда срочно к врачу при боли в груди?",
        "При внезапной давящей боли, одышке, холодном поте — вызывайте скорую, не ждите «само пройдёт».",
    ),
    (
        "Как хранить лекарства дома?",
        "В сухом тёмном месте, вне доступа детей. Следите за сроком годности и не храните в ванной из‑за влаги.",
    ),
    (
        "Нужно ли полоскать горло при ангине?",
        "Тёплые полоскания облегчают симптомы, но при бактериальной ангине без врача антибиотики не назначайте.",
    ),
    (
        "Чем опасен самоназначенный НПВС?",
        "Частый приём ибупрофена или диклофенака без контроля повышает риск язвы и проблем с почками.",
    ),
    (
        "Как правильно измерять сахар?",
        "Натощак или по схеме врача. Руки вымойте, используйте свежие тест-полоски и калиброванный глюкометр.",
    ),
    (
        "Помогает ли прогулка при гипертонии?",
        "Умеренная ходьба 30–40 минут в день полезна давлению, но резкие нагрузки начинайте после консультации.",
    ),
    (
        "Что есть при гастрите?",
        "Дробное питание, тёплая еда без острого и жареного. Кофе и алкоголь лучше ограничить.",
    ),
    (
        "Как снять лёгкую головную боль?",
        "Отдых, вода, проветривание. Если боль сильная, внезапная или с рвотой — обратитесь к врачу.",
    ),
    (
        "Нужна ли маска в сезон гриппа?",
        "В транспорте и людных местах маска снижает риск заражения, особенно при кашле окружающих.",
    ),
    (
        "Как читать инструкцию к лекарству?",
        "Смотрите показания, дозу, противопоказания и взаимодействие с другими препаратами. При сомнении — к врачу.",
    ),
    (
        "Полезен ли контрастный душ?",
        "Многим помогает тонус сосудов, но при гипертонии и болезнях сердца начинайте осторожно и посоветуйтесь с врачом.",
    ),
    (
        "Что делать при изжоге?",
        "Не ложитесь сразу после еды, уменьшите жирное и кофе. Частые приступы — повод к гастроэнтерологу.",
    ),
    (
        "Как ухаживать за зубами?",
        "Чистите 2 раза в день 2 минуты, используйте нить. Раз в полгода — профилактический осмотр у стоматолога.",
    ),
]


class Command(BaseCommand):
    help = (
        "Добавить полезные советы для баннера на главной (ТЗ §7.6). "
        "Пример: python manage.py add_fake_useful_tips --count 15"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=15,
            help="Сколько советов создать (по умолчанию 15, максимум из curated списка).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed (стабильный набор).",
        )
        parser.add_argument(
            "--link-diseases",
            action="store_true",
            help="Случайно привязать часть советов к заболеваниям из справочника.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Сначала удалить все существующие UsefulTip.",
        )
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        count = max(1, min(int(options["count"]), len(CURATED_TIPS)))
        random.seed(options["seed"])

        if options["clear"] and not options["dry_run"]:
            deleted, _ = UsefulTip.objects.all().delete()
            self.stdout.write(f"Удалено старых советов: {deleted}")

        diseases: list[Disease] = []
        if options["link_diseases"]:
            diseases = list(Disease.objects.order_by("name")[:200])

        pool = list(CURATED_TIPS)
        random.shuffle(pool)
        pool = pool[:count]

        created = 0
        updated = 0
        for i, (title, body) in enumerate(pool, start=1):
            disease = None
            if diseases and random.random() < 0.4:
                disease = random.choice(diseases)

            if options["dry_run"]:
                created += 1
                self.stdout.write(f"  [dry-run] {title}")
                continue

            obj, was_created = UsefulTip.objects.update_or_create(
                title=title,
                defaults={
                    "body": body,
                    "disease": disease,
                    "is_active": True,
                    "show_on_home": True,
                    "sort_order": i * 10,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        prefix = "[dry-run] " if options["dry_run"] else ""
        total = UsefulTip.objects.filter(is_active=True, show_on_home=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Полезные советы: +{created} новых, ~{updated} обновлено. "
                f"На главной активно: {total}"
            )
        )
        if options["dry_run"]:
            transaction.set_rollback(True)
