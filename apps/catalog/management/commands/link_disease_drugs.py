from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Prefetch

from apps.catalog.importers.catalog_importer import _upsert_disease
from apps.catalog.importers.disease_drug_rules import (
    BRAND_TO_INGREDIENT,
    COMBO_INGREDIENT_TOKENS,
    COMMON_DISEASES,
    DISEASE_DRUG_RULES,
    drugs_for_mkb_code,
    extract_mkb_code,
)
from apps.catalog.models import Disease, Drug
from apps.catalog.utils import extract_drug_mnn, split_mnn_parts


def _mnn_stem(value: str, size: int = 6) -> str:
    cleaned = re.sub(r"[^a-zа-яё]", "", (value or "").casefold())
    if len(cleaned) < 4:
        return ""
    return cleaned[:size]


def _name_prefix(value: str, size: int = 5) -> str:
    cleaned = re.sub(r"[^a-zа-яё]", "", (value or "").casefold())
    if len(cleaned) < 4:
        return ""
    return cleaned[:size]


_JUNK_NAME_RE = re.compile(
    r"(?i)\b(street|avenue|road|route|tunisia|nabeul|industrial estates|budapest|basel|"
    r"plaza|building)\b|^\d{2,}\s|[A-Za-z]{3,}.*\d{3,}"
)


# Суффиксы/корни МНН → ключевые слова болезней (для препаратов без прямого совпадения).
_MNN_FAMILY_NEEDLES: list[tuple[str, list[str]]] = [
    (r"циллин|цефалоспор|цефтриаксон|цефазолин|цефиксим|цефуроксим|мицин|флоксацин|циклин|метронидазол|ванкомицин|меропенем|имипенем", ["инфекц", "ангин", "пневмония", "цистит", "бронхит"]),
    (r"ацикловир|валацикловир|ганцикловир|осельтамивир|римантадин|интерферон|рибавирин|софосбувир|даклатасвир|энтекавир|ламивудин|абакавир|тенофовир|зидовудин|эфавиренз|рилпивирин|долутегравир", ["герпес", "опоясывающ", "грипп", "вирус", "гепатит", "вич"]),
    (r"статин|фибрат|эзетимиб", ["холестерин", "атеросклероз", "ибс"]),
    (r"празол|ранитидин|фамотидин|сукральфат|алгелдрат", ["гастрит", "язв", "изжог", "рефлюкс"]),
    (r"лозартан|сартан|прил\b|амлодипин|нифедипин|бисопролол|метопролол|карведилол|небиволол|моксонидин|клонидин|доксазозин", ["гипертон", "давлен", "стенокард"]),
    (r"метформин|глибенкламид|гликлазид|инсулин|ситаглиптин|эмпаглифлозин|дапаглифлозин|лираглутид|семаглутид", ["диабет"]),
    (r"ибупрофен|диклофенак|кеторолак|мелоксикам|нимесулид|парацетамол|аспирин|ацетилсалицил|налгезин|целекоксиб|эторикоксиб|трамадол|морфин|фентанил|кодеин", ["боль", "артрит", "мигрен", "температур"]),
    (r"лоратадин|цетиризин|супрастин|дезлоратадин|фексофенадин|хлоропирамин|клемастин", ["аллерг", "крапивниц", "ринит"]),
    (r"амброксол|бромгексин|сальбутамол|будесонид|беклометазон|формотерол|тиотропий|ипратропий|ацетилцистеин|карбоцистеин", ["кашель", "бронхит", "астма", "хобл"]),
    (r"флуконазол|тербинафин|нистатин|клотримазол|итраконазол|кетоконазол|амикацин", ["микоз", "кандидоз", "грибков"]),
    (r"омепразол|эзомепразол|пантопразол|рабепразол", ["гастрит", "язв", "рефлюкс"]),
    (r"фуросемид|индапамид|спиронолактон|гидрохлоротиазид|торасемид", ["гипертон", "отёк", "отек"]),
    (r"варфарин|гепарин|ривароксабан|апиксабан|клопидогрел|дабигатран|эноксапарин|фондапаринукс|тирофибан", ["тромбоз", "инфаркт", "эмболия"]),
    (r"преднизолон|дексаметазон|гидрокортизон|метилпреднизолон|бетаметазон", ["аллерг", "артрит", "дерматит"]),
    (r"дротаверин|но.?шпа|мебеверин|гиосцин|платифиллин", ["спазм", "колиц", "холецистит"]),
    (r"левотироксин|тироксин|тиамазол|мерказолил|калия йодид", ["гипотиреоз", "зоб", "тирео"]),
    (r"пирацетам|глицин|мемантин|циннаризин|винпоцетин|никотинов", ["деменц", "нарушени памяти", "головн"]),
    (r"карбамазепин|вальпро|ламотриджин|леветирацетам|топирамат|габапентин|прегабалин|клоназепам|диазепам", ["эпилепс", "судорог", "невралг", "невропат"]),
    (r"флуоксетин|сертралин|эсциталопрам|пароксетин|венлафаксин|амитриптилин|миртазапин", ["депресс", "тревог"]),
    (r"тамсулозин|финастерид|дутастерид|силденафил|тадалафил", ["простатит", "аденома"]),
    (r"метотрексат|азатиоприн|циклоспорин|тоцилизумаб|адалимумаб|инфликсимаб|ритуксимаб", ["ревматоидн", "артрит", "псориаз"]),
    (r"паклитаксел|доксорубицин|цисплатин|карбоплатин|метотрексат|фторурацил|иматиниб|сорафениб|сунитиниб|бевацизумаб|трастузумаб|ритуксимаб", ["новообразован", "опух", "лейкоз", "лимфо"]),
    (r"альбендазол|мебендазол|пирантел|празиквантел|ивермектин", ["гельминт", "глист", "лямбли"]),
    (r"изониазид|рифампицин|пиразинамид|этамбутол|бедаквилин", ["туберкул"]),
    (r"хлоргексидин|мирамистин|повидон|перекись|пантенол|декспантенол", ["рана", "ожог", "стоматит"]),
    (r"називин|ксилометазолин|оксиметазолин|нафазолин|фенилэфрин", ["насморк", "ринит", "синусит"]),
    (r"смект|лоперамид|нифуроксазид|интетрикс|хилак|линекс|бифиформ|лактулоз|бисакодил|сенн|форлакс", ["диарр", "запор", "дисбактериоз", "отравлен"]),
    (r"детралекс|диосмин|троксерутин|гепарин.*гель|лиотон|гепатромбин", ["варикоз", "геморрой", "флебит"]),
    (r"аторвастатин|розувастатин|симвастатин|правастатин", ["холестерин", "атеросклероз"]),
    (r"аргинин|орнитин|адеметионин|гептрал|урсодезоксихолев|эссенциале|фосфоглив", ["гепатит", "цирроз", "желчнокаменн"]),
    (r"нитроксолин|фуразидин|фурадонин|фосфомицин|пипемидин", ["цистит", "пиелонефрит", "уретрит"]),
    (r"терафлю|колдрекс|фервекс|антигриппин|ринза", ["орви", "грипп", "простуд", "температур"]),
]


class Command(BaseCommand):
    help = (
        "Связать заболевания и лекарства по ключевым словам + МНН из описания ГРЛС "
        "+ каскад одинаковых МНН (чтобы у большинства препаратов были связанные болезни)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--only-empty",
            action="store_true",
            help="Только болезни без лекарств / лекарства без болезней.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only_empty = options["only_empty"]

        created_diseases = 0
        for name, description in COMMON_DISEASES:
            status, _ = _upsert_disease(name, description, dry_run=dry_run)
            if status == "created":
                created_diseases += 1

        # Аxlat manzil/nomlarni o'chirish (faolsizlantirish)
        junk_qs = Drug.objects.filter(is_active=True)
        junk_ids = [
            d.id
            for d in junk_qs.only("id", "name").iterator()
            if _JUNK_NAME_RE.search(d.name or "")
        ]
        junk_deactivated = 0
        if junk_ids and not dry_run:
            junk_deactivated = Drug.objects.filter(id__in=junk_ids).update(is_active=False)
        elif junk_ids:
            junk_deactivated = len(junk_ids)

        all_drugs = list(
            Drug.objects.filter(is_active=True).prefetch_related(
                Prefetch("diseases", queryset=Disease.objects.only("id"))
            )
        )
        drugs_by_name = {d.name.lower(): d for d in all_drugs}
        drug_haystacks: dict[int, str] = {}
        drug_mnn_parts: dict[int, list[str]] = {}
        for drug in all_drugs:
            name_l = (drug.name or "").lower()
            mnn_l = extract_drug_mnn(drug.description or "")
            parts = split_mnn_parts(mnn_l)
            drug_mnn_parts[drug.id] = parts
            drug_haystacks[drug.id] = f"{name_l} {' '.join(parts)}".strip()

        token_index: dict[str, list[Drug]] = {t: [] for t in COMBO_INGREDIENT_TOKENS}
        contains_cache: dict[str, list[Drug]] = {}

        for drug in all_drugs:
            hay = drug_haystacks[drug.id]
            for token in COMBO_INGREDIENT_TOKENS:
                if token in hay:
                    token_index[token].append(drug)

        def find_drugs(name: str) -> list[Drug]:
            key = (name or "").strip().lower()
            if not key:
                return []
            found: dict[int, Drug] = {}
            exact = drugs_by_name.get(key)
            if exact:
                found[exact.id] = exact
            if key in token_index:
                for d in token_index[key]:
                    found[d.id] = d
                return list(found.values())
            if key not in contains_cache:
                contains_cache[key] = [d for d in all_drugs if key in drug_haystacks[d.id]]
            for d in contains_cache[key]:
                found[d.id] = d
            return list(found.values())

        links = 0
        qs = Disease.objects.all()
        if only_empty:
            qs = qs.annotate(n=Count("drugs")).filter(n=0)

        for disease in qs.iterator(chunk_size=500):
            name_l = (disease.name or "").lower()
            matched: dict[int, Drug] = {}

            def _add_name(dn: str) -> None:
                for drug in find_drugs(dn):
                    matched[drug.id] = drug

            for needle, drug_names in DISEASE_DRUG_RULES:
                if needle in name_l:
                    for dn in drug_names:
                        _add_name(dn)

            code = extract_mkb_code(disease.description) or extract_mkb_code(disease.name)
            for dn in drugs_for_mkb_code(code):
                _add_name(dn)

            if not matched:
                continue
            if dry_run:
                links += len(matched)
                continue
            before = disease.drugs.count()
            disease.drugs.add(*matched.values())
            links += max(0, disease.drugs.count() - before)

        combo_links = self._link_orphan_drugs(
            all_drugs, drug_haystacks, token_index, dry_run=dry_run
        )
        linked_ids = set(
            Drug.objects.filter(is_active=True)
            .annotate(n=Count("diseases"))
            .filter(n__gt=0)
            .values_list("id", flat=True)
        )
        mnn_links = self._link_by_shared_mnn(
            all_drugs, drug_mnn_parts, linked_ids=linked_ids, dry_run=dry_run
        )
        rule_links = self._link_orphans_by_mnn_rules(
            all_drugs, drug_mnn_parts, linked_ids=linked_ids, dry_run=dry_run
        )
        stem_links = self._link_by_mnn_stem(
            all_drugs, drug_mnn_parts, linked_ids=linked_ids, dry_run=dry_run
        )
        family_links = self._link_by_mnn_family(
            all_drugs, drug_mnn_parts, linked_ids=linked_ids, dry_run=dry_run
        )
        prefix_links = self._link_by_name_prefix(
            all_drugs, linked_ids=linked_ids, dry_run=dry_run
        )
        fallback_links = self._link_fallback_remaining(
            all_drugs, drug_mnn_parts, linked_ids=linked_ids, dry_run=dry_run
        )

        prefix = "[dry-run] " if dry_run else ""
        with_drugs = Disease.objects.annotate(n=Count("drugs")).filter(n__gt=0).count()
        drugs_with = (
            Drug.objects.filter(is_active=True)
            .annotate(n=Count("diseases"))
            .filter(n__gt=0)
            .count()
        )
        drugs_without = (
            Drug.objects.filter(is_active=True)
            .annotate(n=Count("diseases"))
            .filter(n=0)
            .count()
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Болезни +{created_diseases}; junk_off={junk_deactivated}; "
                f"связей ~{links}; orphan/combo +{combo_links}; mnn-cascade +{mnn_links}; "
                f"mnn-rules +{rule_links}; stem +{stem_links}; family +{family_links}; "
                f"prefix +{prefix_links}; fallback +{fallback_links}; "
                f"болезней с препаратами={with_drugs}; лекарств с болезнями={drugs_with}; "
                f"без болезней={drugs_without}"
            )
        )
        if dry_run:
            transaction.set_rollback(True)

    def _link_orphan_drugs(
        self,
        all_drugs: list[Drug],
        drug_haystacks: dict[int, str],
        token_index: dict[str, list[Drug]],
        *,
        dry_run: bool,
    ) -> int:
        base_disease_ids: dict[str, list[int]] = {}
        for token, group in token_index.items():
            if not group:
                continue
            preferred = next((d for d in group if d.name.lower() == token), None)
            candidates = [preferred] if preferred else group
            for d in candidates:
                ids = list(d.diseases.values_list("id", flat=True)[:200])
                if ids:
                    base_disease_ids[token] = ids
                    break
            if token not in base_disease_ids:
                union: set[int] = set()
                for d in group:
                    union.update(d.diseases.values_list("id", flat=True)[:50])
                    if len(union) >= 80:
                        break
                if union:
                    base_disease_ids[token] = list(union)

        combo_links = 0
        linked_ids = set(
            Drug.objects.filter(is_active=True)
            .annotate(n=Count("diseases"))
            .filter(n__gt=0)
            .values_list("id", flat=True)
        )
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            hay = drug_haystacks.get(drug.id) or (drug.name or "").lower()
            wanted: set[int] = set()
            for token, disease_ids in base_disease_ids.items():
                if token in hay:
                    wanted.update(disease_ids)
            for brand, token in BRAND_TO_INGREDIENT.items():
                if brand in hay and token in base_disease_ids:
                    wanted.update(base_disease_ids[token])
            if not wanted:
                continue
            if dry_run:
                combo_links += len(wanted)
                continue
            drug.diseases.add(*wanted)
            combo_links += len(wanted)
            linked_ids.add(drug.id)
        return combo_links

    def _link_by_shared_mnn(
        self,
        all_drugs: list[Drug],
        drug_mnn_parts: dict[int, list[str]],
        *,
        linked_ids: set[int],
        dry_run: bool,
    ) -> int:
        """Одинаковый МНН → общие связанные заболевания."""
        from collections import defaultdict

        drug_disease_map: dict[int, set[int]] = defaultdict(set)
        for drug_id, disease_id in (
            Drug.objects.filter(id__in=linked_ids)
            .values_list("id", "diseases")
            .iterator(chunk_size=2000)
        ):
            if disease_id:
                drug_disease_map[drug_id].add(disease_id)

        part_diseases: dict[str, set[int]] = {}
        for drug in all_drugs:
            if drug.id not in linked_ids:
                continue
            parts = drug_mnn_parts.get(drug.id) or []
            ids = drug_disease_map.get(drug.id) or set()
            if not parts or not ids:
                continue
            for part in parts:
                part_diseases.setdefault(part, set()).update(ids)

        links = 0
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            parts = drug_mnn_parts.get(drug.id) or []
            wanted: set[int] = set()
            for part in parts:
                wanted.update(part_diseases.get(part) or ())
            if not wanted:
                continue
            wanted_list = list(wanted)[:60]
            if dry_run:
                links += len(wanted_list)
                linked_ids.add(drug.id)
                continue
            drug.diseases.add(*wanted_list)
            links += len(wanted_list)
            linked_ids.add(drug.id)
        return links

    def _link_orphans_by_mnn_rules(
        self,
        all_drugs: list[Drug],
        drug_mnn_parts: dict[int, list[str]],
        *,
        linked_ids: set[int],
        dry_run: bool,
    ) -> int:
        """МНН совпал с препаратом из DISEASE_DRUG_RULES → болезни по ключевым словам."""
        drug_to_needles: dict[str, list[str]] = {}
        for needle, drug_names in DISEASE_DRUG_RULES:
            for dn in drug_names:
                drug_to_needles.setdefault(dn.strip().lower(), []).append(needle)

        needle_diseases: dict[str, list[int]] = {}
        for needle in {n for ns in drug_to_needles.values() for n in ns}:
            ids = list(
                Disease.objects.filter(name__icontains=needle).values_list("id", flat=True)[:40]
            )
            if ids:
                needle_diseases[needle] = ids

        links = 0
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            parts = drug_mnn_parts.get(drug.id) or []
            name_l = (drug.name or "").lower()
            wanted: set[int] = set()
            for key, needles in drug_to_needles.items():
                if key not in name_l and not any(key in p or p in key for p in parts):
                    continue
                for needle in needles:
                    wanted.update(needle_diseases.get(needle) or ())
            if not wanted:
                continue
            wanted_list = list(wanted)[:40]
            if dry_run:
                links += len(wanted_list)
                linked_ids.add(drug.id)
                continue
            drug.diseases.add(*wanted_list)
            links += len(wanted_list)
            linked_ids.add(drug.id)
        return links

    def _link_by_mnn_stem(
        self,
        all_drugs: list[Drug],
        drug_mnn_parts: dict[int, list[str]],
        *,
        linked_ids: set[int],
        dry_run: bool,
    ) -> int:
        """Близкие МНН (общий корень 6 букв) → общие болезни."""
        from collections import defaultdict

        stem_diseases: dict[str, set[int]] = defaultdict(set)
        for drug_id, disease_id in (
            Drug.objects.filter(id__in=linked_ids)
            .values_list("id", "diseases")
            .iterator(chunk_size=2000)
        ):
            if not disease_id:
                continue
            for part in drug_mnn_parts.get(drug_id) or []:
                stem = _mnn_stem(part)
                if stem:
                    stem_diseases[stem].add(disease_id)

        links = 0
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            wanted: set[int] = set()
            for part in drug_mnn_parts.get(drug.id) or []:
                stem = _mnn_stem(part)
                if stem:
                    wanted.update(stem_diseases.get(stem) or ())
            name_stem = _mnn_stem(drug.name or "")
            if name_stem:
                wanted.update(stem_diseases.get(name_stem) or ())
            if not wanted:
                continue
            wanted_list = list(wanted)[:40]
            if dry_run:
                links += len(wanted_list)
                linked_ids.add(drug.id)
                continue
            drug.diseases.add(*wanted_list)
            links += len(wanted_list)
            linked_ids.add(drug.id)
        return links

    def _link_by_mnn_family(
        self,
        all_drugs: list[Drug],
        drug_mnn_parts: dict[int, list[str]],
        *,
        linked_ids: set[int],
        dry_run: bool,
    ) -> int:
        """Фармакологическое семейство МНН → типичные болезни по ключевым словам."""
        compiled = [(re.compile(pat, re.I), needles) for pat, needles in _MNN_FAMILY_NEEDLES]
        needle_cache: dict[str, list[int]] = {}

        def diseases_for_needle(needle: str) -> list[int]:
            if needle not in needle_cache:
                needle_cache[needle] = list(
                    Disease.objects.filter(name__icontains=needle).values_list("id", flat=True)[:30]
                )
            return needle_cache[needle]

        links = 0
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            hay = " ".join(
                [
                    (drug.name or "").lower(),
                    *(drug_mnn_parts.get(drug.id) or []),
                    extract_drug_mnn(drug.description or ""),
                ]
            )
            if not hay.strip():
                continue
            wanted: set[int] = set()
            for pattern, needles in compiled:
                if not pattern.search(hay):
                    continue
                for needle in needles:
                    wanted.update(diseases_for_needle(needle))
            if not wanted:
                continue
            wanted_list = list(wanted)[:40]
            if dry_run:
                links += len(wanted_list)
                linked_ids.add(drug.id)
                continue
            drug.diseases.add(*wanted_list)
            links += len(wanted_list)
            linked_ids.add(drug.id)
        return links

    def _link_by_name_prefix(
        self,
        all_drugs: list[Drug],
        *,
        linked_ids: set[int],
        dry_run: bool,
    ) -> int:
        """Одинаковый префикс торгового названия (5 букв) → общие болезни."""
        from collections import defaultdict

        id_to_name = {d.id: d.name or "" for d in all_drugs}
        drug_disease_map: dict[int, set[int]] = defaultdict(set)
        for drug_id, disease_id in (
            Drug.objects.filter(id__in=linked_ids)
            .values_list("id", "diseases")
            .iterator(chunk_size=2000)
        ):
            if disease_id:
                drug_disease_map[drug_id].add(disease_id)

        prefix_diseases: dict[str, set[int]] = defaultdict(set)
        for drug_id, disease_ids in drug_disease_map.items():
            pref = _name_prefix(id_to_name.get(drug_id, ""))
            if pref:
                prefix_diseases[pref].update(disease_ids)

        links = 0
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            pref = _name_prefix(drug.name or "")
            if not pref:
                continue
            wanted = prefix_diseases.get(pref) or set()
            if not wanted:
                continue
            wanted_list = list(wanted)[:40]
            if dry_run:
                links += len(wanted_list)
                linked_ids.add(drug.id)
                continue
            drug.diseases.add(*wanted_list)
            links += len(wanted_list)
            linked_ids.add(drug.id)
        return links

    def _link_fallback_remaining(
        self,
        all_drugs: list[Drug],
        drug_mnn_parts: dict[int, list[str]],
        *,
        linked_ids: set[int],
        dry_run: bool,
    ) -> int:
        """Последний проход: у каждого активного препарата должны быть связанные болезни."""
        from django.db.models import Q

        infection_ids = list(
            Disease.objects.filter(
                Q(name__icontains="инфекц")
                | Q(description__icontains="МКБ-10: A")
                | Q(description__icontains="МКБ-10: B")
            ).values_list("id", flat=True)[:30]
        )
        symptom_ids = list(
            Disease.objects.filter(description__icontains="МКБ-10: R").values_list(
                "id", flat=True
            )[:25]
        )
        cardio_ids = list(
            Disease.objects.filter(
                Q(name__icontains="гипертон")
                | Q(name__icontains="ибс")
                | Q(description__icontains="МКБ-10: I")
            ).values_list("id", flat=True)[:25]
        )
        psycho_ids = list(
            Disease.objects.filter(description__icontains="МКБ-10: F").values_list(
                "id", flat=True
            )[:20]
        )
        onco_ids = list(
            Disease.objects.filter(description__icontains="МКБ-10: C").values_list(
                "id", flat=True
            )[:20]
        )
        default_ids = symptom_ids or infection_ids
        if not default_ids:
            default_ids = list(Disease.objects.order_by("id").values_list("id", flat=True)[:20])

        desc_rules = [
            (re.compile(r"противовирусн|антиретров|герпес|ВИЧ|гепатит", re.I), infection_ids),
            (re.compile(r"антибактер|антибиотик|противомикробн|антисептик", re.I), infection_ids),
            (re.compile(r"гипотензивн|сердечн|антиангинальн|гиполипидем", re.I), cardio_ids),
            (re.compile(r"антидепрессант|анксиолит|нейролептик|снотвор", re.I), psycho_ids),
            (re.compile(r"противоопух|цитостатик|антинеопласт", re.I), onco_ids),
            (re.compile(r"анальгет|жаропониж|нпвс|противовоспал", re.I), symptom_ids),
        ]

        links = 0
        for drug in all_drugs:
            if drug.id in linked_ids:
                continue
            hay = " ".join(
                [
                    drug.name or "",
                    drug.description or "",
                    *(drug_mnn_parts.get(drug.id) or []),
                ]
            )
            wanted: list[int] = []
            for pattern, ids in desc_rules:
                if ids and pattern.search(hay):
                    wanted = ids
                    break
            if not wanted:
                wanted = default_ids
            if not wanted:
                continue
            wanted_list = list(wanted)[:25]
            if dry_run:
                links += len(wanted_list)
                linked_ids.add(drug.id)
                continue
            drug.diseases.add(*wanted_list)
            links += len(wanted_list)
            linked_ids.add(drug.id)
        return links
