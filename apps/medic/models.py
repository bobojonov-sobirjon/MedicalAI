from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class City(models.Model):
    """ТЗ §7.13: справочник городов для учреждений (в API сортировка А–Я)."""

    class GeoLevel(models.TextChoices):
        REGION = "region", "Область/регион"
        CITY = "city", "Город"
        DISTRICT = "district", "Район"

    name = models.CharField("Город", max_length=128, unique=True)
    geo_level = models.CharField(
        "Тип",
        max_length=16,
        choices=GeoLevel.choices,
        default=GeoLevel.CITY,
    )
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Город"
        verbose_name_plural = "Города"
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class MedicalFacility(models.Model):
    class Kind(models.TextChoices):
        PHARMACY = "pharmacy", "Аптека"
        HOSPITAL = "hospital", "Больница"

    kind = models.CharField("Тип", max_length=16, choices=Kind.choices)
    city = models.ForeignKey(City, verbose_name="Город", on_delete=models.CASCADE, related_name="facilities")
    name = models.CharField("Название", max_length=255)
    address = models.CharField("Адрес", max_length=512, blank=True, default="")
    phone = models.CharField("Телефон", max_length=64, blank=True, default="")
    hours_text = models.CharField("Часы работы", max_length=255, blank=True, default="")
    description = models.TextField("Описание", blank=True, default="")
    latitude = models.DecimalField("Широта", max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField("Долгота", max_digits=10, decimal_places=7, null=True, blank=True)
    image = models.ImageField("Изображение", upload_to="facilities/", blank=True, null=True)
    external_source = models.CharField("Источник", max_length=32, blank=True, default="")
    external_id = models.CharField("Внешний ID", max_length=128, blank=True, default="")
    is_active = models.BooleanField("Активно", default=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Мед. учреждение"
        verbose_name_plural = "Мед. учреждения"
        indexes = [
            models.Index(fields=["kind", "city", "name"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("external_source", "external_id"),
                condition=models.Q(external_source__gt="", external_id__gt=""),
                name="uniq_facility_external_source_id",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.get_kind_display()})"


class UsefulTip(models.Model):
    """ТЗ §5.5 / §7.12.2 — полезные советы (опционально привязаны к болезни)."""

    disease = models.ForeignKey(
        "catalog.Disease",
        verbose_name="Заболевание",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="useful_tips",
    )
    title = models.CharField("Заголовок", max_length=255)
    body = models.TextField("Текст")
    is_active = models.BooleanField("Включено", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Полезный совет"
        verbose_name_plural = "Полезные советы"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:  # pragma: no cover
        return self.title


class UsefulFeedSeen(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="useful_seen",
    )
    last_seen_at = models.DateTimeField("Последний просмотр", auto_now=True)

    class Meta:
        verbose_name = "Просмотр «Полезное»"
        verbose_name_plural = "Просмотры «Полезное»"


class AppUpdateBroadcast(models.Model):
    """ТЗ §8.2.2 — обновление приложения (попадает во вкладку «Полезное»)."""

    title = models.CharField("Заголовок", max_length=255, default="Обновление MedicAi")
    body = models.TextField("Список изменений")
    published_at = models.DateTimeField("Опубликовано", auto_now_add=True)
    send_push = models.BooleanField("Отправить push (заглушка)", default=False)

    class Meta:
        verbose_name = "Обновление программы"
        verbose_name_plural = "Обновления программы"
        ordering = ["-published_at"]


class UserTipSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="tip_settings",
    )
    tips_per_day = models.PositiveSmallIntegerField("Советов в сутки", default=3)
    useful_subscribed = models.BooleanField("Подписка на полезное", default=False)

    class Meta:
        verbose_name = "Настройки советов"
        verbose_name_plural = "Настройки советов"


class DiseaseTipSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="disease_tip_subs",
    )
    disease = models.ForeignKey(
        "catalog.Disease",
        verbose_name="Заболевание",
        on_delete=models.CASCADE,
        related_name="tip_subscribers",
    )
    is_active = models.BooleanField("Активна", default=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Подписка на советы по болезни"
        verbose_name_plural = "Подписки на советы по болезни"
        unique_together = [("user", "disease")]


class NotificationEvent(models.Model):
    """ТЗ §7.12.1 — события и напоминания пользователя."""

    class Kind(models.TextChoices):
        SYSTEM = "system", "Система"
        HOSPITAL = "hospital", "Больница"
        REMINDER = "reminder", "Напоминание"
        UPDATE = "update", "Обновление"
        USEFUL = "useful", "Полезное"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Получатель",
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Для кого (профиль)",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_events_as_subject",
        help_text="Опционально: конкретный профиль (семейный аккаунт), к которому относится событие.",
    )
    subject_user_label = models.CharField("Для кого (подпись)", max_length=128, blank=True, default="")
    kind = models.CharField("Тип", max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField("Заголовок", max_length=255)
    body = models.TextField("Текст", blank=True, default="")
    link_url = models.URLField("Ссылка", blank=True, default="")
    event_at = models.DateTimeField("Событие / напоминание", null=True, blank=True)
    notify_at = models.DateTimeField("Уведомить в", null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="Родительское событие",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="scheduled_children",
        help_text="Для расписанных уведомлений (1 сутки/3ч/2ч/1ч) — ссылка на исходное событие.",
    )
    notify_offsets_min = models.JSONField("Смещения (мин)", default=list, blank=True)
    meta = models.JSONField("Метаданные", default=dict, blank=True)
    read_at = models.DateTimeField("Прочитано", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Событие / уведомление"
        verbose_name_plural = "События"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "notify_at"]),
            models.Index(fields=["recipient", "parent"]),
        ]


class StaticPage(models.Model):
    """ТЗ §7.15–7.16 — статические страницы (о компании, конфиденциальность)."""

    slug = models.SlugField("Код", max_length=64, unique=True)
    title = models.CharField("Заголовок", max_length=255)
    body = models.TextField("Текст")
    is_active = models.BooleanField("Активна", default=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Статическая страница"
        verbose_name_plural = "Статические страницы"

    def __str__(self) -> str:  # pragma: no cover
        return self.slug


class FeedbackTicket(models.Model):
    """ТЗ §7.17.2 — обратная связь (хранится в БД; письмо отправляется из view)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_tickets",
    )
    email = models.EmailField("Эл. почта", blank=True, default="")
    subject = models.CharField("Тема", max_length=255, blank=True, default="")
    message = models.TextField("Сообщение")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Обратная связь"
        verbose_name_plural = "Обратная связь"
        ordering = ["-created_at"]


class PsychologyInquiry(models.Model):
    """ТЗ §7.18 — вопрос психологу."""

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        IN_PROGRESS = "in_progress", "В работе"
        CLOSED = "closed", "Закрыт"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="psych_inquiries",
    )
    message = models.TextField("Сообщение")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.NEW)

    class Meta:
        verbose_name = "Вопрос психологу"
        verbose_name_plural = "Вопросы психологу"
        ordering = ["-created_at"]


class ChatThread(models.Model):
    """ТЗ §7.17.1 — чат поддержки (REST; WebSocket позже)."""

    class Status(models.TextChoices):
        OPEN = "open", "Открыт"
        CLOSED = "closed", "Закрыт"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="chat_threads",
    )
    title = models.CharField("Тема", max_length=255, blank=True, default="Поддержка")
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.OPEN)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Чат поддержки"
        verbose_name_plural = "Чаты поддержки"
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    thread = models.ForeignKey(
        ChatThread,
        verbose_name="Чат",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Отправитель",
        on_delete=models.CASCADE,
        related_name="chat_messages_sent",
    )
    is_staff = models.BooleanField("Сообщение сотрудника", default=False)
    body = models.TextField("Текст")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение чата"
        verbose_name_plural = "Сообщения чата"
        ordering = ["created_at"]


class DrugReview(models.Model):
    """ТЗ §5.7.1 / §7.10.2 — отзывы (модерация)."""

    class Status(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Одобрен"
        REJECTED = "rejected", "Отклонён"

    drug = models.ForeignKey("catalog.Drug", verbose_name="Лекарство", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="drug_reviews",
    )
    rating = models.PositiveSmallIntegerField("Оценка", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("Текст отзыва")
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.CharField("Причина отклонения", max_length=255, blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Отзыв на лекарство"
        verbose_name_plural = "Отзывы на лекарства"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["drug", "status", "-created_at"])]


class DrugUserStarRating(models.Model):
    """ТЗ §8.2.4 — 1 оценка (звёзды) на пользователя и лекарство; менять раз в 24 часа."""

    drug = models.ForeignKey("catalog.Drug", verbose_name="Лекарство", on_delete=models.CASCADE, related_name="user_star_ratings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="drug_star_ratings",
    )
    stars = models.PositiveSmallIntegerField("Звёзды", validators=[MinValueValidator(1), MaxValueValidator(5)])
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Оценка лекарства пользователем"
        verbose_name_plural = "Оценки лекарств"
        constraints = [models.UniqueConstraint(fields=("drug", "user"), name="uniq_drug_user_star")]


class DrugDiscussionThread(models.Model):
    drug = models.OneToOneField(
        "catalog.Drug",
        verbose_name="Лекарство",
        on_delete=models.CASCADE,
        related_name="discussion_thread",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Обсуждение лекарства"
        verbose_name_plural = "Обсуждения лекарств"


class DiscussionPost(models.Model):
    thread = models.ForeignKey(
        DrugDiscussionThread,
        verbose_name="Обсуждение",
        on_delete=models.CASCADE,
        related_name="posts",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Автор", on_delete=models.CASCADE)
    body = models.TextField("Сообщение")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение обсуждения"
        verbose_name_plural = "Сообщения обсуждений"
        ordering = ["created_at"]


class RelaxAsset(models.Model):
    """ТЗ §5.9 / §7.21 — контент для «Релакс»."""

    class Category(models.TextChoices):
        GIF = "gif", "Гиф-анимация"
        VIDEO = "video", "Видео"
        MUSIC = "music", "Музыка"

    category = models.CharField("Категория", max_length=16, choices=Category.choices)
    title = models.CharField("Название", max_length=255, blank=True, default="")
    file = models.FileField("Файл", upload_to="relax/", blank=True, null=True)
    external_url = models.URLField("Внешняя ссылка", blank=True, default="")
    is_active = models.BooleanField("Активно", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Контент «Релакс»"
        verbose_name_plural = "Контент «Релакс»"
        ordering = ["sort_order", "id"]


class FaqItem(models.Model):
    """ТЗ §6.1 — база вопрос/ответ для рекомендаций."""

    question = models.CharField("Вопрос", max_length=512)
    answer = models.TextField("Ответ")
    disease = models.ForeignKey(
        "catalog.Disease",
        verbose_name="Заболевание",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="faq_items",
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Вопрос-ответ"
        verbose_name_plural = "Вопросы-ответы (FAQ)"


class DrugAnalog(models.Model):
    """ТЗ §8.2.3 — аналоги (заполняются парсером/админкой)."""

    drug = models.ForeignKey("catalog.Drug", verbose_name="Лекарство", on_delete=models.CASCADE, related_name="analog_rows")
    name = models.CharField("Название аналога", max_length=255)
    price = models.DecimalField("Цена", max_digits=12, decimal_places=2, null=True, blank=True)
    source_url = models.URLField("Ссылка на источник", blank=True, default="")

    class Meta:
        verbose_name = "Аналог лекарства"
        verbose_name_plural = "Аналоги лекарств"


class Survey(models.Model):
    """ТЗ §8.2.3 — всплывающий опрос (создаётся в админке)."""

    class AnswerType(models.TextChoices):
        YES_NO = "yes_no", "Да / Нет"
        TEXT = "text", "Текст"
        CHOICE = "choice", "Выбор из списка"

    slug = models.SlugField("Код", max_length=64, unique=True)
    title = models.CharField("Название (админка)", max_length=255, blank=True, default="")
    question_text = models.CharField("Вопрос", max_length=512)
    answer_type = models.CharField(
        "Тип ответа",
        max_length=16,
        choices=AnswerType.choices,
        default=AnswerType.YES_NO,
    )
    choices = models.JSONField(
        "Варианты (для choice)",
        default=list,
        blank=True,
        help_text='Например: ["Да", "Нет"]',
    )
    profile_field = models.CharField(
        "Поле профиля",
        max_length=64,
        blank=True,
        default="",
        help_text="При ответе синхронизировать с профилем, напр. had_covid",
    )
    is_active = models.BooleanField("Активен", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Опрос"
        verbose_name_plural = "Опросы"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.title or self.question_text[:80]


class SurveyResponse(models.Model):
    """ТЗ §8.2.4 — ответ пользователя на опрос."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="survey_responses",
    )
    survey = models.ForeignKey(
        Survey,
        verbose_name="Опрос",
        on_delete=models.CASCADE,
        related_name="responses",
    )
    answers = models.JSONField("Ответы", default=dict)
    comment = models.TextField("Комментарий", blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Ответ на опрос"
        verbose_name_plural = "Ответы на опросы"
        constraints = [
            models.UniqueConstraint(fields=["user", "survey"], name="uniq_survey_response_per_user"),
        ]


class AuditLogEntry(models.Model):
    """ТЗ §3.9 — аудит действий пользователя (часть)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField("Действие", max_length=64)
    path = models.CharField("Путь", max_length=512, blank=True, default="")
    metadata = models.JSONField("Метаданные", default=dict, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Аудит"
        verbose_name_plural = "Журнал аудита"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]


class ApiErrorLog(models.Model):
    """ТЗ §3.9 — ошибки API (5xx и другие исключения)."""

    status_code = models.PositiveSmallIntegerField("Код ответа", null=True, blank=True)
    message = models.TextField("Сообщение", blank=True, default="")
    path = models.CharField("Путь", max_length=512, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Ошибка API"
        verbose_name_plural = "Ошибки API"
        ordering = ["-created_at"]


class SearchQueryLog(models.Model):
    """ТЗ §5.1 — аналитика поисковых запросов."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    source = models.CharField("Источник", max_length=32)
    query_text = models.CharField("Текст запроса", max_length=512)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Поисковый запрос"
        verbose_name_plural = "Поисковые запросы"
        ordering = ["-created_at"]
