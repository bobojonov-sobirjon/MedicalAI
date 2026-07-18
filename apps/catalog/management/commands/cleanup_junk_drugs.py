"""Скрыть (is_active=False) мусорные импортированные лекарства.

Безопасно: НИЧЕГО НЕ УДАЛЯЕТ. По умолчанию dry-run — только показывает, что будет скрыто.
Запуск с изменениями: --apply. Вернуть всё обратно: --restore.

Мусор = латинские названия (нет кириллицы), пустое описание / «Источник: …»,
нумерованные дубликаты (Abacavir 1..17), косметика и т.п.
Реальные препараты (кириллица + осмысленное описание ИЛИ связанные болезни) не трогаем.
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.catalog.models import Drug

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_JUNK_DESC_PREFIXES = ("источник",)


class Command(BaseCommand):
    help = "Скрыть мусорные лекарства (латиница/без описания). По умолчанию dry-run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения (иначе только показать).",
        )
        parser.add_argument(
            "--restore",
            action="store_true",
            help="Вернуть все лекарства в is_active=True.",
        )

    def handle(self, *args, **options):
        if options["restore"]:
            n = Drug.objects.filter(is_active=False).update(is_active=True)
            self.stdout.write(self.style.SUCCESS(f"Восстановлено (is_active=True): {n}"))
            return

        apply = options["apply"]
        # Кандидаты в мусор: неактивные ещё не трогаем, только активные.
        qs = Drug.objects.filter(is_active=True).annotate(n_dis=Count("diseases"))

        to_hide_ids: list[int] = []
        kept = 0
        for drug in qs.iterator(chunk_size=1000):
            if self._is_junk(drug):
                to_hide_ids.append(drug.id)
            else:
                kept += 1

        total = qs.count()
        self.stdout.write(f"Активных лекарств: {total}")
        self.stdout.write(f"  Оставляем (реальные): {kept}")
        self.stdout.write(f"  Кандидаты скрыть (мусор): {len(to_hide_ids)}")

        # Примеры
        sample = Drug.objects.filter(id__in=to_hide_ids[:15]).values_list("name", flat=True)
        for name in sample:
            self.stdout.write(f"    - {name}")

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "\nЭто DRY-RUN. Ничего не изменено.\n"
                    "Применить: python manage.py cleanup_junk_drugs --apply\n"
                    "Вернуть:  python manage.py cleanup_junk_drugs --restore"
                )
            )
            return

        hidden = 0
        # Батчами
        for i in range(0, len(to_hide_ids), 2000):
            batch = to_hide_ids[i : i + 2000]
            hidden += Drug.objects.filter(id__in=batch).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f"Скрыто (is_active=False): {hidden}"))
        shown = Drug.objects.filter(is_active=True).count()
        self.stdout.write(self.style.SUCCESS(f"Осталось видимых в приложении: {shown}"))

    def _is_junk(self, drug: Drug) -> bool:
        name = (drug.name or "").strip()
        desc = (drug.description or "").strip().lower()

        # Реальные: есть связанные болезни -> НЕ мусор
        if getattr(drug, "n_dis", 0) > 0:
            return False

        has_cyrillic = bool(_CYRILLIC_RE.search(name))
        has_real_desc = bool(desc) and not desc.startswith(_JUNK_DESC_PREFIXES)

        # Кириллическое название + осмысленное описание -> реальный препарат
        if has_cyrillic and has_real_desc:
            return False

        # Латиница в названии -> мусор (Vidal-транслит)
        if not has_cyrillic:
            return True

        # Кириллица, но без описания и без болезней -> тоже скрываем (пустышка)
        if not has_real_desc:
            return True

        return False
