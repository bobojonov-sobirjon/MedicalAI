from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class City(models.Model):
    """ТЗ §7.13: справочник городов для учреждений (в API сортировка А–Я)."""

    name = models.CharField("Город", max_length=128, unique=True)
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
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image = models.ImageField("Изображение", upload_to="facilities/", blank=True, null=True)
    external_source = models.CharField("Источник", max_length=32, blank=True, default="")
    external_id = models.CharField("Внешний ID", max_length=128, blank=True, default="")
    is_active = models.BooleanField("Активно", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Мед. учреждение"
        verbose_name_plural = "Мед. учреждения"
        indexes = [
            models.Index(fields=["kind", "city", "name"]),
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
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
        on_delete=models.CASCADE,
        related_name="tip_settings",
    )
    tips_per_day = models.PositiveSmallIntegerField("Советов в сутки", default=3)
    useful_subscribed = models.BooleanField("Подписка на полезное", default=False)

    class Meta:
        verbose_name = "Настройки советов"
        verbose_name_plural = "Настройки советов"


class DiseaseTipSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="disease_tip_subs")
    disease = models.ForeignKey("catalog.Disease", on_delete=models.CASCADE, related_name="tip_subscribers")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Подписка на советы по болезни"
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
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    link_url = models.URLField(blank=True, default="")
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
    created_at = models.DateTimeField(auto_now_add=True)

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
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Статическая страница"
        verbose_name_plural = "Статические страницы"

    def __str__(self) -> str:  # pragma: no cover
        return self.slug


class FeedbackTicket(models.Model):
    """ТЗ §7.17.2 — обратная связь (хранится в БД; письмо отправляется из view)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_tickets",
    )
    email = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Обратная связь"
        ordering = ["-created_at"]


class PsychologyInquiry(models.Model):
    """ТЗ §7.18 — вопрос психологу."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="psych_inquiries")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, default="new")

    class Meta:
        verbose_name = "Вопрос психологу"
        ordering = ["-created_at"]


class ChatThread(models.Model):
    """ТЗ §7.17.1 — чат поддержки (REST; WebSocket позже)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_threads")
    title = models.CharField(max_length=255, blank=True, default="Поддержка")
    status = models.CharField(max_length=16, default="open")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Чат поддержки"
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages_sent")
    is_staff = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение чата"
        ordering = ["created_at"]


class DrugReview(models.Model):
    """ТЗ §5.7.1 / §7.10.2 — отзывы (модерация)."""

    class Status(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Одобрен"
        REJECTED = "rejected", "Отклонён"

    drug = models.ForeignKey("catalog.Drug", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drug_reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Отзыв на лекарство"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["drug", "status", "-created_at"])]


class DrugUserStarRating(models.Model):
    """ТЗ §8.2.4 — 1 оценка (звёзды) на пользователя и лекарство; менять раз в 24 часа."""

    drug = models.ForeignKey("catalog.Drug", on_delete=models.CASCADE, related_name="user_star_ratings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drug_star_ratings")
    stars = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Оценка лекарства пользователем"
        constraints = [models.UniqueConstraint(fields=("drug", "user"), name="uniq_drug_user_star")]


class DrugDiscussionThread(models.Model):
    drug = models.OneToOneField("catalog.Drug", on_delete=models.CASCADE, related_name="discussion_thread")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Обсуждение лекарства"


class DiscussionPost(models.Model):
    thread = models.ForeignKey(DrugDiscussionThread, on_delete=models.CASCADE, related_name="posts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение обсуждения"
        ordering = ["created_at"]


class RelaxAsset(models.Model):
    """ТЗ §5.9 / §7.21 — контент для «Релакс»."""

    class Category(models.TextChoices):
        GIF = "gif", "GIF"
        VIDEO = "video", "Видео"

    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(upload_to="relax/", blank=True, null=True)
    external_url = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Релакс контент"
        ordering = ["sort_order", "id"]


class FaqItem(models.Model):
    """ТЗ §6.1 — база вопрос/ответ для рекомендаций."""

    question = models.CharField(max_length=512)
    answer = models.TextField()
    disease = models.ForeignKey(
        "catalog.Disease",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="faq_items",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Вопрос-ответ"


class DrugAnalog(models.Model):
    """ТЗ §8.2.3 — аналоги (заполняются парсером/админкой)."""

    drug = models.ForeignKey("catalog.Drug", on_delete=models.CASCADE, related_name="analog_rows")
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    source_url = models.URLField(blank=True, default="")

    class Meta:
        verbose_name = "Аналог лекарства"


class SurveyResponse(models.Model):
    """ТЗ §8.2.4 — ответы на всплывающий опрос."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="survey_responses")
    slug = models.SlugField(max_length=64)
    answers = models.JSONField(default=dict)
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ответ на опрос"


class AuditLogEntry(models.Model):
    """ТЗ §3.9 — аудит действий пользователя (часть)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    path = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Аудит"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"])]


class ApiErrorLog(models.Model):
    """ТЗ §3.9 — ошибки API (5xx и другие исключения)."""

    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    message = models.TextField(blank=True, default="")
    path = models.CharField(max_length=512, blank=True, default="")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ошибка API"
        ordering = ["-created_at"]


class SearchQueryLog(models.Model):
    """ТЗ §5.1 — аналитика поисковых запросов."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    source = models.CharField(max_length=32)
    query_text = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Поисковый запрос"
        ordering = ["-created_at"]
