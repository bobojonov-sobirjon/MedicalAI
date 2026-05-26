"""
Демо-данные для всех основных моделей MedicAI.

Запуск:
  python manage.py seed_demo_data
  python manage.py seed_demo_data --count 30
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from apps.accounts.models import FamilyLink
from apps.assistant.models import AssistantDiagnosis
from apps.cabinet.models import CabinetItem
from apps.catalog.models import BodyPart, Disease, Drug, Symptom
from apps.history.models import Analysis, DiseaseRecord, DoctorVisit, Prescription
from apps.medic.models import (
    AppUpdateBroadcast,
    ChatMessage,
    ChatThread,
    City,
    DrugAnalog,
    DiscussionPost,
    DrugDiscussionThread,
    DrugReview,
    DrugUserStarRating,
    FaqItem,
    FeedbackTicket,
    MedicalFacility,
    NotificationEvent,
    PsychologyInquiry,
    RelaxAsset,
    StaticPage,
    Survey,
    SurveyResponse,
    UsefulTip,
    UserTipSettings,
)

User = get_user_model()

BODY_PARTS = [
    ("head", "Голова", 10),
    ("neck", "Шея", 20),
    ("body", "Тело", 30),
    ("left_arm", "Левая рука", 40),
    ("right_arm", "Правая рука", 50),
    ("leg", "Нога", 60),
]

SYMPTOMS = [
    ("Головная боль", "боль в голове"),
    ("Кашель", "покашливание"),
    ("Тошнота", ""),
    ("Слабость", "усталость"),
    ("Насморк", "ринит"),
]

RELAX_SAMPLES = [
    (RelaxAsset.Category.GIF, "Спокойное дыхание", "https://upload.wikimedia.org/wikipedia/commons/2/2c/Rotating_earth_%28large%29.gif"),
    (RelaxAsset.Category.GIF, "Морская волна", "https://media.giphy.com/media/3o7abKhOpu0NwenH3O/giphy.gif"),
    (RelaxAsset.Category.VIDEO, "Природа — ручей", "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"),
    (RelaxAsset.Category.VIDEO, "Медитация", "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4"),
    (RelaxAsset.Category.MUSIC, "Белый шум", "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"),
    (RelaxAsset.Category.MUSIC, "Релакс-трек", "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3"),
]

STATIC_PAGES = [
    ("about", "О компании", "MedicAI — персональный медицинский помощник."),
    ("privacy", "Конфиденциальность", "Мы бережно храним ваши персональные данные."),
]

FAQ_SAMPLES = [
    ("Что делать при головной боли?", "Отдохните, пейте воду. При ухудшении — к врачу."),
    ("Как измерить давление?", "Измеряйте в покое, сидя, два раза с интервалом."),
]


class Command(BaseCommand):
    help = "Заполнить БД демо-данными (все основные модели, русские тексты)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=25, help="Сколько записей на сущность (где применимо).")
        parser.add_argument("--seed", type=int, default=42, help="Seed для воспроизводимости.")

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        seed: int = options["seed"]
        random.seed(seed)
        fake = Faker("ru_RU")
        Faker.seed(seed)

        self.stdout.write("Справочники и части тела…")
        for code, label, sort_order in BODY_PARTS:
            BodyPart.objects.update_or_create(code=code, defaults={"label": label, "sort_order": sort_order})
        for name, aliases in SYMPTOMS:
            Symptom.objects.get_or_create(name=name, defaults={"aliases": aliases})

        diseases: list[Disease] = []
        for i in range(count):
            name = f"{fake.word().capitalize()} {fake.word().capitalize()}"
            d, _ = Disease.objects.get_or_create(name=name, defaults={"description": fake.text(max_nb_chars=200)})
            diseases.append(d)

        drugs: list[Drug] = []
        dosages = ["100 мг", "250 мг", "500 мг", "5 мл", "1 таб.", "2 таб."]
        for i in range(count):
            name = f"{fake.word().capitalize()}-{fake.word().capitalize()}"
            drug, _ = Drug.objects.get_or_create(
                name=name,
                defaults={"description": fake.text(max_nb_chars=300), "dosage": random.choice(dosages), "rating": Decimal("4.0")},
            )
            if diseases:
                drug.diseases.set(random.sample(diseases, k=min(3, len(diseases))))
            drugs.append(drug)

        self.stdout.write("Города и медучреждения…")
        cities = []
        for name in ["Ташкент", "Самарканд", "Бухара", "Москва", "Санкт-Петербург"]:
            c, _ = City.objects.get_or_create(name=name)
            cities.append(c)

        for i in range(min(count, 15)):
            city = random.choice(cities)
            kind = random.choice([MedicalFacility.Kind.PHARMACY, MedicalFacility.Kind.HOSPITAL])
            MedicalFacility.objects.get_or_create(
                name=f"{'Аптека' if kind == 'pharmacy' else 'Больница'} «{fake.company()}»",
                city=city,
                defaults={
                    "kind": kind,
                    "address": fake.address().replace("\n", ", ")[:200],
                    "phone": fake.phone_number()[:32],
                    "hours_text": "пн–сб 9:00–18:00 | вс 10:00–16:00",
                    "description": fake.text(max_nb_chars=180),
                    "latitude": Decimal(str(round(random.uniform(41.2, 41.4), 7))),
                    "longitude": Decimal(str(round(random.uniform(69.1, 69.4), 7))),
                    "is_active": True,
                },
            )

        self.stdout.write("Контент: советы, страницы, FAQ, релакс…")
        for d in diseases[:5]:
            UsefulTip.objects.get_or_create(
                title=f"Совет при {d.name[:40]}",
                defaults={"body": fake.text(max_nb_chars=400), "disease": d, "is_active": True},
            )

        for slug, title, body in STATIC_PAGES:
            StaticPage.objects.update_or_create(slug=slug, defaults={"title": title, "body": body, "is_active": True})

        for q, a in FAQ_SAMPLES:
            FaqItem.objects.get_or_create(question=q, defaults={"answer": a, "is_active": True})

        for idx, (cat, title, url) in enumerate(RELAX_SAMPLES):
            RelaxAsset.objects.get_or_create(
                title=title,
                category=cat,
                defaults={"external_url": url, "is_active": True, "sort_order": idx * 10},
            )
        for i in range(6):
            cat = random.choice([RelaxAsset.Category.GIF, RelaxAsset.Category.VIDEO, RelaxAsset.Category.MUSIC])
            RelaxAsset.objects.get_or_create(
                title=f"Демо {cat.label} #{i + 1}",
                category=cat,
                defaults={
                    "external_url": RELAX_SAMPLES[i % len(RELAX_SAMPLES)][2],
                    "is_active": True,
                    "sort_order": 100 + i,
                },
            )

        AppUpdateBroadcast.objects.get_or_create(
            title="Обновление MedicAi",
            defaults={"body": "• Улучшен раздел «Релакс»\n• Семейные профили\n• Исправления ошибок"},
        )

        self.stdout.write("Пользователи и семья…")
        owner, _ = User.objects.get_or_create(
            username="demo_user",
            defaults={
                "email": "demo@medicai.local",
                "first_name": "Иван",
                "last_name": "Демидов",
                "city": "Ташкент",
                "is_active": True,
            },
        )
        if not owner.has_usable_password():
            owner.set_password("demo12345")
            owner.save(update_fields=["password"])

        member, _ = User.objects.get_or_create(
            username="demo_family_mama",
            defaults={"first_name": "Анна", "last_name": "Демидова", "gender": "female", "is_active": True},
        )
        member.set_unusable_password()
        member.save(update_fields=["password"])
        FamilyLink.objects.get_or_create(owner=owner, member=member, defaults={"label": "Мама"})

        UserTipSettings.objects.get_or_create(user=owner, defaults={"tips_per_day": 3, "useful_subscribed": True})

        self.stdout.write("История, аптечка, уведомления…")
        for u in [owner, member]:
            for _ in range(3):
                dis = random.choice(diseases) if diseases else None
                rec = DiseaseRecord.objects.create(
                    user=owner,
                    subject_user=u,
                    disease=dis,
                    title=dis.name if dis else fake.sentence(nb_words=4),
                    symptoms=fake.text(max_nb_chars=120),
                    date_of_illness=date.today() - timedelta(days=random.randint(1, 400)),
                )
                if drugs:
                    rec.drugs.set(random.sample(drugs, k=min(2, len(drugs))))
                DoctorVisit.objects.create(
                    record=rec,
                    visit_date=rec.date_of_illness,
                    specialty="Терапевт",
                    doctor_full_name=fake.name(),
                    diagnosis=fake.sentence(),
                )
                Analysis.objects.create(
                    record=rec,
                    taken_date=rec.date_of_illness,
                    name="Общий анализ крови",
                    result_text="В пределах нормы",
                )
                Prescription.objects.create(record=rec, note="Рецепт демо")

        for _ in range(min(10, len(drugs))):
            drug = random.choice(drugs)
            CabinetItem.objects.get_or_create(
                user=owner,
                drug=drug,
                defaults={"expires_at": date.today() + timedelta(days=random.randint(30, 400))},
            )

        NotificationEvent.objects.get_or_create(
            recipient=owner,
            title="Добро пожаловать в MedicAI",
            defaults={
                "body": "Заполните профиль для точных рекомендаций.",
                "kind": NotificationEvent.Kind.SYSTEM,
                "subject_user": owner,
            },
        )

        self.stdout.write("Отзывы, обсуждения, поддержка…")
        for drug in drugs[:8]:
            DrugReview.objects.get_or_create(
                drug=drug,
                user=owner,
                defaults={
                    "rating": random.randint(3, 5),
                    "text": fake.text(max_nb_chars=200),
                    "status": DrugReview.Status.APPROVED,
                },
            )
            DrugUserStarRating.objects.update_or_create(
                drug=drug, user=owner, defaults={"stars": random.randint(4, 5)}
            )
            th, _ = DrugDiscussionThread.objects.get_or_create(drug=drug)
            if not th.posts.filter(user=owner).exists():
                DiscussionPost.objects.create(
                    thread=th,
                    user=owner,
                    body="Помогает, принимаю по назначению врача.",
                )
            DrugAnalog.objects.get_or_create(
                drug=drug,
                name=f"Аналог {fake.word().capitalize()}",
                defaults={"price": Decimal(str(random.randint(100, 2500)))},
            )

        FeedbackTicket.objects.get_or_create(
            user=owner,
            subject="Демо обращение",
            defaults={"email": owner.email or "demo@local", "message": fake.text(max_nb_chars=300)},
        )
        PsychologyInquiry.objects.get_or_create(
            user=owner,
            defaults={"message": "Как справиться со стрессом перед экзаменами?", "status": PsychologyInquiry.Status.NEW},
        )
        thread, _ = ChatThread.objects.get_or_create(user=owner, defaults={"title": "Поддержка MedicAI"})
        ChatMessage.objects.get_or_create(
            thread=thread, sender=owner, defaults={"body": "Здравствуйте, нужна помощь с приложением.", "is_staff": False}
        )

        covid_survey, _ = Survey.objects.get_or_create(
            slug="had_covid",
            defaults={
                "title": "COVID-19",
                "question_text": "Болели Covid-19?",
                "answer_type": Survey.AnswerType.YES_NO,
                "profile_field": "had_covid",
                "sort_order": 1,
            },
        )
        Survey.objects.get_or_create(
            slug="onboarding",
            defaults={
                "title": "Онбординг",
                "question_text": "Насколько понятно приложение?",
                "answer_type": Survey.AnswerType.CHOICE,
                "choices": ["1", "2", "3", "4", "5"],
                "sort_order": 2,
            },
        )
        SurveyResponse.objects.get_or_create(
            user=owner,
            survey=covid_survey,
            defaults={"answers": {"value": True}, "comment": ""},
        )

        symptom_ids = list(Symptom.objects.values_list("id", flat=True)[:3])
        body_ids = list(BodyPart.objects.values_list("id", flat=True)[:2])
        AssistantDiagnosis.objects.get_or_create(
            user=owner,
            subject_user=member,
            defaults={
                "symptom_ids": symptom_ids,
                "symptoms_text": "лёгкая слабость",
                "body_part_ids": body_ids,
                "temperature_c": 36.6,
                "blood_pressure": "120/80",
                "result": {
                    "ai": {
                        "summary": "Демо-результат помощника.",
                        "possible_conditions": [],
                        "suggested_next_steps": ["Обратитесь к врачу при ухудшении."],
                        "disclaimer": "Не является медицинской консультацией.",
                    }
                },
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Готово. Демо-пользователь: demo_user / пароль: demo12345"))
        self.stdout.write(self.style.SUCCESS(f"Заболеваний: {Disease.objects.count()}, лекарств: {Drug.objects.count()}"))
        self.stdout.write(self.style.SUCCESS(f"Релакс: {RelaxAsset.objects.count()}, FAQ: {FaqItem.objects.count()}"))
