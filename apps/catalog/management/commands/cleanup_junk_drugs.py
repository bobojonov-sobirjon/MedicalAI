"""Скрыть (is_active=False) НЕ-лекарства: косметику, вакцины, латинский мусор.

Безопасно и КОНСЕРВАТИВНО: НИЧЕГО НЕ УДАЛЯЕТ и НЕ трогает реальные препараты,
даже если у них пока нет описания (Эликвис, Цитрамон, Пирацетам остаются).
По умолчанию dry-run. Применить: --apply. Вернуть: --restore.

Скрываем только:
  • латиница в названии (нет кириллицы) — транслит-остатки Vidal;
  • косметику/уходовые бренды (Авен Клинанс, Виши, дезодоранты, шампуни, пилинги);
  • вакцины (это не препараты для самолечения по каталогу).
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.catalog.models import Drug

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

# Явные НЕ-лекарства по подстроке в названии (нижний регистр).
_JUNK_NAME_TOKENS = (
    # вакцины
    "вакцин",
    "vaccine",
    "анатоксин",
    "сыворотк",
    # косметические бренды / линейки
    "клинанс",
    "ксеракалм",
    "авен ",
    "виши",
    "vichy",
    "биодерма",
    "bioderma",
    "ля рош",
    "la roche",
    "либридерм",
    "эуцерин",
    "eucerin",
    "нивея",
    "nivea",
    "рексона",
    "лореаль",
    "l'oreal",
    "garnier",
    "гарньер",
    # уходовые формы
    "шампунь",
    "гель для душа",
    "дезодорант",
    "антиперспирант",
    "пилинг",
    "скраб",
    "мицеллярн",
    "тоник для",
    "маска для лица",
    "крем для лица",
    "крем для рук",
    "крем для ног",
    "лосьон для",
    "бальзам для губ",
    "зубная паста",
    "средство для умывания",
)


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
        name_l = name.lower()

        # Реальные: есть связанные болезни -> НИКОГДА не скрываем
        if getattr(drug, "n_dis", 0) > 0:
            return False

        # Явные НЕ-лекарства (косметика/вакцины) по ключевым словам
        if any(tok in name_l for tok in _JUNK_NAME_TOKENS):
            return True

        # Латиница в названии (нет кириллицы) -> транслит-остаток
        if not _CYRILLIC_RE.search(name):
            return True

        # Всё остальное — реальный препарат, оставляем ВИДИМЫМ,
        # даже если описание пока пустое (его можно дополнить позже).
        return False
