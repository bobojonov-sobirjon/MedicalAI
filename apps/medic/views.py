from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Drug
from apps.catalog.serializers import DrugSerializer

from .models import (
    AppUpdateBroadcast,
    ChatMessage,
    ChatThread,
    City,
    DiscussionPost,
    DiseaseTipSubscription,
    DrugAnalog,
    DrugDiscussionThread,
    DrugReview,
    DrugUserStarRating,
    FaqItem,
    FeedbackTicket,
    MedicalFacility,
    NotificationEvent,
    PsychologyInquiry,
    SearchQueryLog,
    StaticPage,
    UsefulTip,
    UsefulFeedSeen,
    UserTipSettings,
)
from .utils_profanity import contains_profanity

User = get_user_model()
from apps.accounts.models import CustomUser, FamilyLink


def _ensure_reminder_children(user: User) -> None:
    """
    TZ §8.2.3 (events): уведомления за 1 сутки / 3 часа / 2 часа / 1 час.
    Реализовано без фонового воркера: дочерние уведомления создаются «лениво»
    при чтении ленты/бейджа.
    """
    now = timezone.now()
    offsets = [1440, 180, 120, 60]

    parents = list(
        NotificationEvent.objects.filter(
            recipient=user,
            kind=NotificationEvent.Kind.REMINDER,
            parent__isnull=True,
            event_at__isnull=False,
        ).order_by("-created_at")[:200]
    )
    if not parents:
        return

    for p in parents:
        parent_offsets = p.notify_offsets_min or offsets
        # normalize
        try:
            parent_offsets = [int(x) for x in parent_offsets]
        except Exception:
            parent_offsets = offsets
        parent_offsets = [x for x in parent_offsets if x > 0]
        if not parent_offsets:
            parent_offsets = offsets

        for off in parent_offsets:
            notify_at = p.event_at - timedelta(minutes=int(off))
            if notify_at > now:
                continue
            exists = NotificationEvent.objects.filter(
                recipient=user,
                parent=p,
                meta__offset_min=int(off),
            ).exists()
            if exists:
                continue
            NotificationEvent.objects.create(
                recipient=user,
                subject_user=p.subject_user,
                subject_user_label=p.subject_user_label,
                kind=NotificationEvent.Kind.REMINDER,
                title=p.title,
                body=p.body,
                link_url=p.link_url,
                event_at=p.event_at,
                notify_at=notify_at,
                parent=p,
                meta={"offset_min": int(off)},
            )


# --- Geo ---
class CityListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Медучреждения"],
        summary="Список городов (А–Я)",
        description=(
            "Flutter city picker loads the list **once without `q`** and filters locally.\n"
            "Therefore without `q` the API returns **all cities that have facilities** "
            "(incl. small towns like Янаул), not only ~137 majors.\n"
            "With `q` — server-side substring search."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=False,
                description="Поиск города по подстроке (обязательно для UI-поля поиска)",
            ),
            OpenApiParameter(
                name="level",
                type=str,
                required=False,
                description="region | city | district (по умолчанию city)",
            ),
            OpenApiParameter(name="limit", required=False, type=int, description="Лимит (по умолчанию 200/500)"),
            OpenApiParameter(
                name="with_facilities",
                type=bool,
                required=False,
                description="true — только города, где есть активные учреждения",
            ),
        ],
    )
    def get(self, request):
        from django.db.models import Count, Q

        from apps.medic.importers.city_normalize import is_blocked_city_name
        from apps.medic.city_quality import is_latin_only_city_name

        q = (request.query_params.get("q") or "").strip()
        level = (request.query_params.get("level") or "city").strip().lower()
        with_facilities_raw = (request.query_params.get("with_facilities") or "").strip().lower()

        level_map = {
            "region": City.GeoLevel.REGION,
            "city": City.GeoLevel.CITY,
            "district": City.GeoLevel.DISTRICT,
        }
        geo_level = level_map.get(level, City.GeoLevel.CITY)

        # Flutter city sheet: loads GET /geo/cities/ once WITHOUT q, then filters locally.
        # So without q we must return ALL towns that have facilities (incl. Янаул),
        # not only the curated ~137 majors — otherwise «яна» finds nothing.
        full_catalog = not q
        if with_facilities_raw in {"1", "true", "yes", "y"}:
            with_facilities = True
        elif with_facilities_raw in {"0", "false", "no", "n"}:
            with_facilities = False
        else:
            with_facilities = True  # default: only cities with pharmacies/hospitals

        try:
            default_limit = 20000 if full_catalog else 500
            limit = int(request.query_params.get("limit") or default_limit)
        except (TypeError, ValueError):
            limit = 20000 if full_catalog else 500
        limit = min(max(limit, 1), 30000)

        rows = City.objects.filter(geo_level=geo_level)
        if q:
            rows = rows.filter(name__icontains=q)

        rows = rows.annotate(
            facilities_count=Count(
                "facilities",
                filter=Q(facilities__is_active=True),
                distinct=True,
            )
        )
        if with_facilities:
            rows = rows.filter(facilities_count__gt=0)

        # Majors first, then A–Я
        rows = rows.order_by("-sort_order", "name")

        payload = []
        for c in rows.iterator(chunk_size=1000):
            if is_blocked_city_name(c.name) or is_latin_only_city_name(c.name):
                continue
            payload.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "geo_level": c.geo_level,
                    "facilities_count": int(getattr(c, "facilities_count", 0) or 0),
                }
            )
            if len(payload) >= limit:
                break

        return Response(payload)


def _facility_image_url(request, obj: "MedicalFacility") -> str | None:
    from apps.core.media_urls import file_field_url

    stored = file_field_url(request, obj.image if getattr(obj, "image", None) else None)
    if stored:
        return stored
    # Нет сохранённой картинки — отдаём статичную карту по координатам (как в списке аптек).
    if obj.latitude is not None and obj.longitude is not None:
        from apps.medic.importers.facility_image_resolver import yandex_static_map_url

        try:
            return yandex_static_map_url(obj.latitude, obj.longitude)
        except (TypeError, ValueError):
            return None
    return None


def _facility_map_url(obj: "MedicalFacility") -> str | None:
    """Build a convenient Google Maps link for the facility."""
    if obj.latitude is not None and obj.longitude is not None:
        return f"https://www.google.com/maps/search/?api=1&query={obj.latitude},{obj.longitude}"
    if obj.address:
        from urllib.parse import quote_plus

        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(obj.address)}"
    return None


class FacilityListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Медучреждения"],
        summary="Аптеки / больницы",
        parameters=[
            OpenApiParameter(
                name="kind",
                type=str,
                required=False,
                description="Тип учреждения: pharmacy (аптека) или hospital (больница)",
            ),
            OpenApiParameter(
                name="city_id",
                type=int,
                required=False,
                description="Идентификатор города (список: GET /api/geo/cities/)",
            ),
            OpenApiParameter(
                name="q",
                type=str,
                required=False,
                description="Поиск по названию или адресу. Цифры (напр. 40) ищут «ГКБ №40».",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                required=False,
                description="Лимит (по умолчанию 500, максимум 2000)",
            ),
            OpenApiParameter(
                name="lat",
                type=float,
                required=False,
                description="Широта пользователя — сортировка по близости (ближайшие сверху).",
            ),
            OpenApiParameter(
                name="lon",
                type=float,
                required=False,
                description="Долгота пользователя — вместе с lat сортирует по близости.",
            ),
        ],
    )
    def get(self, request):
        kind = (request.query_params.get("kind") or "").strip()
        city_id = request.query_params.get("city_id")
        q = (request.query_params.get("q") or "").strip()
        try:
            limit = min(int(request.query_params.get("limit") or 500), 2000)
        except (TypeError, ValueError):
            limit = 500

        def _parse_coord(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        lat0 = _parse_coord(request.query_params.get("lat"))
        lon0 = _parse_coord(request.query_params.get("lon"))

        qs = MedicalFacility.objects.filter(is_active=True).select_related("city")
        if kind in ("pharmacy", "hospital"):
            qs = qs.filter(kind=kind)
        if city_id and str(city_id).isdigit():
            qs = qs.filter(city_id=int(city_id))

        near_sorted = False
        if lat0 is not None and lon0 is not None and not q:
            from django.db.models import ExpressionWrapper, F, FloatField
            from django.db.models.functions import Cast

            lat_f = Cast("latitude", FloatField())
            lon_f = Cast("longitude", FloatField())
            # Приближённое квадрат-расстояние (для сортировки внутри города достаточно).
            qs = (
                qs.filter(latitude__isnull=False, longitude__isnull=False)
                .annotate(
                    _dist=ExpressionWrapper(
                        (lat_f - lat0) * (lat_f - lat0)
                        + (lon_f - lon0) * (lon_f - lon0) * 0.34,
                        output_field=FloatField(),
                    )
                )
                .order_by("_dist")
            )
            near_sorted = True

        if q:
            from django.db.models import Case, IntegerField, Value, When

            cond = Q(name__icontains=q) | Q(address__icontains=q)
            # «40» → ГКБ №40 / Больница 40 / № 40 (как в Яндекс.Картах)
            digits = "".join(ch for ch in q if ch.isdigit())
            if digits and (q == digits or len(digits) >= 1):
                for pattern in (
                    f"№{digits}",
                    f"№ {digits}",
                    f"N{digits}",
                    f"N {digits}",
                    f"No.{digits}",
                    f"No {digits}",
                    f" {digits}",
                    f"{digits} ",
                    f"-{digits}",
                    f"{digits}-",
                ):
                    cond |= Q(name__icontains=pattern)
            qs = qs.filter(cond).annotate(
                _rank=Case(
                    When(name__iexact=q, then=Value(0)),
                    When(name__istartswith=q, then=Value(1)),
                    When(name__icontains=q, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            ).order_by("_rank", "name")
        elif not near_sorted:
            qs = qs.order_by("name")

        data = [
            {
                "id": o.id,
                "kind": o.kind,
                "name": o.name,
                "address": o.address,
                # Backward compatibility: старый Flutter читает именно phone/hours_text.
                "phone": o.phone or "Телефон не указан",
                "phone_raw": o.phone,
                "phone_display": o.phone or "Телефон не указан",
                "phone_available": bool(o.phone),
                "hours_text": o.hours_text or "Режим работы не указан",
                "hours_raw": o.hours_text,
                "hours_display": o.hours_text or "Режим работы не указан",
                "hours_available": bool(o.hours_text),
                "description": o.description,
                "image_url": _facility_image_url(request, o),
                "latitude": str(o.latitude) if o.latitude is not None else None,
                "longitude": str(o.longitude) if o.longitude is not None else None,
                "city_id": o.city_id,
                "city_name": o.city.name,
            }
            for o in qs[:limit]
        ]
        return Response(data)


class FacilityDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Медучреждения"], summary="Карточка учреждения")
    def get(self, request, pk: int):
        o = MedicalFacility.objects.select_related("city").filter(pk=pk, is_active=True).first()
        if not o:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "id": o.id,
                "kind": o.kind,
                "name": o.name,
                "address": o.address,
                # Backward compatibility: старый Flutter читает именно phone/hours_text.
                "phone": o.phone or "Телефон не указан",
                "phone_raw": o.phone,
                "phone_display": o.phone or "Телефон не указан",
                "phone_available": bool(o.phone),
                "hours_text": o.hours_text or "Режим работы не указан",
                "hours_raw": o.hours_text,
                "hours_display": o.hours_text or "Режим работы не указан",
                "hours_available": bool(o.hours_text),
                "description": o.description,
                "image_url": _facility_image_url(request, o),
                "map_url": _facility_map_url(o),
                "latitude": str(o.latitude) if o.latitude is not None else None,
                "longitude": str(o.longitude) if o.longitude is not None else None,
                "city": {"id": o.city_id, "name": o.city.name},
            }
        )


# --- Content ---
class StaticPageView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Контент"],
        summary="Статическая страница по коду",
        description="Текст для экранов «О компании», «Конфиденциальность» и др. Slug задаётся в админке (например about, privacy).",
    )
    def get(self, request, slug: str):
        p = StaticPage.objects.filter(slug=slug, is_active=True).first()
        if not p:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"slug": p.slug, "title": p.title, "body": p.body})


class AppConfigView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Контент"],
        summary="Публичные настройки приложения",
        description="Срок бесплатного периода (дни), контакт психолога и др. без авторизации.",
    )
    def get(self, request):
        return Response(
            {
                "free_trial_days": int(getattr(settings, "FREE_TRIAL_DAYS", 1)),
                "psychology_email": getattr(settings, "PSYCHOLOGY_EMAIL", "psychology@medic-ai.ru"),
            }
        )


# --- Tips & notifications ---
def _tip_payload(request, tip: UsefulTip) -> dict:
    from apps.core.media_urls import file_field_url

    return {
        "id": tip.id,
        "title": tip.title,
        "body": tip.body,
        "image_url": file_field_url(request, tip.image if tip.image else None),
        "disease_id": tip.disease_id,
        "sort_order": tip.sort_order,
        "updated_at": tip.updated_at or tip.created_at,
    }


class HomeUsefulTipsView(APIView):
    """ТЗ §7.6 — баннер полезных советов на главной странице ЛК."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Полезные советы"],
        summary="Советы для баннера на главной (карусель)",
        description=(
            "ТЗ §7.6 / §5.5: список активных советов для блока вверху главной. "
            "Админ добавляет советы в «Полезные советы». "
            "`home_tips_hidden=true` — блок скрыт; на клиенте показывать только «?», "
            "по нажатию вызвать PATCH /api/me/tip-settings/ с `home_tips_hidden: false`."
        ),
        responses={
            200: inline_serializer(
                name="HomeUsefulTipsResponse",
                fields={
                    "home_tips_hidden": serializers.BooleanField(),
                    "tips": serializers.ListField(child=serializers.DictField()),
                },
            ),
        },
    )
    def get(self, request):
        settings_obj, _ = UserTipSettings.objects.get_or_create(user=request.user)
        tips = (
            UsefulTip.objects.filter(is_active=True, show_on_home=True)
            .order_by("sort_order", "id")[:30]
        )
        return Response(
            {
                "home_tips_hidden": settings_obj.home_tips_hidden,
                "tips": [_tip_payload(request, t) for t in tips],
            }
        )


class UsefulCombinedFeedView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Уведомления"],
        summary="Вкладка «Полезное»: советы + обновления",
        description=(
            "Возвращает полезные советы и обновления приложения. "
            "Советы видны только при активной подписке пользователя. "
            "Для логики колокольчика (unread в «Полезное») используйте "
            "`GET /api/me/notifications/badge/` и отметку просмотра "
            "`POST /api/me/notifications/useful/seen/`."
        ),
    )
    def get(self, request):
        out = []
        for u in AppUpdateBroadcast.objects.order_by("-published_at")[:20]:
            out.append({"type": "update", "id": u.id, "title": u.title, "body": u.body, "at": u.published_at})
        if request.user.useful_tips_subscribed:
            tips = UsefulTip.objects.filter(is_active=True).order_by("sort_order", "id")[:50]
            for t in tips:
                payload = _tip_payload(request, t)
                payload["type"] = "tip"
                payload["at"] = payload.pop("updated_at")
                out.append(payload)
        return Response(out)


class UsefulMarkSeenView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Уведомления"],
        summary="Отметить вкладку «Полезное» просмотренной",
        description="Нужно для логики колокольчика (unread в «Полезное»). Тело запроса не требуется.",
        request=inline_serializer(name="UsefulMarkSeenEmptyBody", fields={}),
        responses={200: inline_serializer(name="UsefulMarkSeenOk", fields={"ok": serializers.BooleanField()})},
    )
    def post(self, request):
        UsefulFeedSeen.objects.update_or_create(user=request.user, defaults={})
        return Response({"ok": True})


class UserTipSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Полезные советы"],
        summary="Настройки советов (лимит, подписка, скрытие баннера на главной)",
        responses={
            200: inline_serializer(
                name="UserTipSettingsGet",
                fields={
                    "tips_per_day": serializers.IntegerField(),
                    "useful_subscribed": serializers.BooleanField(),
                    "home_tips_hidden": serializers.BooleanField(),
                },
            ),
        },
    )
    def get(self, request):
        obj, _ = UserTipSettings.objects.get_or_create(user=request.user)
        return Response(
            {
                "tips_per_day": obj.tips_per_day,
                "useful_subscribed": obj.useful_subscribed,
                "home_tips_hidden": obj.home_tips_hidden,
            }
        )

    @extend_schema(
        tags=["Полезные советы"],
        summary="Обновить настройки советов / скрыть-показать баннер на главной",
        description=(
            "ТЗ §7.6: скрыть блок советов — `home_tips_hidden: true`. "
            "Показать снова (знак «?» на главной) — `home_tips_hidden: false`."
        ),
        request=inline_serializer(
            name="UserTipSettingsPatch",
            fields={
                "tips_per_day": serializers.IntegerField(
                    required=False,
                    min_value=1,
                    max_value=20,
                    help_text="Сколько советов в сутки показывать (1–20).",
                ),
                "useful_subscribed": serializers.BooleanField(
                    required=False,
                    help_text="Подписка на вкладку «Полезное».",
                ),
                "home_tips_hidden": serializers.BooleanField(
                    required=False,
                    help_text="Скрыть баннер советов на главной (true) / показать (false).",
                ),
            },
        ),
        responses={
            200: inline_serializer(
                name="UserTipSettingsResponse",
                fields={
                    "tips_per_day": serializers.IntegerField(),
                    "useful_subscribed": serializers.BooleanField(),
                    "home_tips_hidden": serializers.BooleanField(),
                },
            ),
        },
    )
    def patch(self, request):
        obj, _ = UserTipSettings.objects.get_or_create(user=request.user)
        if "tips_per_day" in request.data:
            v = int(request.data["tips_per_day"])
            obj.tips_per_day = max(1, min(v, 20))
        if "useful_subscribed" in request.data:
            obj.useful_subscribed = bool(request.data["useful_subscribed"])
            request.user.useful_tips_subscribed = obj.useful_subscribed
            request.user.save(update_fields=["useful_tips_subscribed"])
        if "home_tips_hidden" in request.data:
            raw = request.data["home_tips_hidden"]
            if isinstance(raw, str):
                obj.home_tips_hidden = raw.strip().lower() in {"1", "true", "yes", "on"}
            else:
                obj.home_tips_hidden = bool(raw)
        obj.save()
        return Response(
            {
                "tips_per_day": obj.tips_per_day,
                "useful_subscribed": obj.useful_subscribed,
                "home_tips_hidden": obj.home_tips_hidden,
            }
        )


class DiseaseTipSubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Уведомления"],
        summary="Подписаться на советы по болезни",
        description="Тело запроса не используется — `disease_id` передаётся в пути URL.",
        request=inline_serializer(name="DiseaseTipSubscribeEmptyBody", fields={}),
        responses={200: inline_serializer(name="DiseaseTipSubscribeOk", fields={"ok": serializers.BooleanField()})},
    )
    def post(self, request, disease_id: int):
        DiseaseTipSubscription.objects.update_or_create(
            user=request.user,
            disease_id=disease_id,
            defaults={"is_active": True},
        )
        return Response({"ok": True})

    @extend_schema(tags=["Уведомления"], summary="Отписаться от советов по болезни")
    def delete(self, request, disease_id: int):
        DiseaseTipSubscription.objects.filter(user=request.user, disease_id=disease_id).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationEventListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    class NotificationEventCreateSerializer(serializers.Serializer):
        title = serializers.CharField(required=False, allow_blank=True, help_text="Заголовок; по умолчанию «Напоминание».")
        body = serializers.CharField(required=False, allow_blank=True)
        event_at = serializers.DateTimeField(
            required=False,
            allow_null=True,
            help_text="Дата/время события (ISO 8601).",
        )
        subject_user_id = serializers.IntegerField(
            required=False,
            allow_null=True,
            min_value=1,
            help_text="ID профиля (семейный аккаунт). Должен быть владельцем или привязанным профилем.",
        )
        subject_user_label = serializers.CharField(
            required=False,
            allow_blank=True,
            max_length=128,
            help_text="Подпись «для кого» (семейный профиль).",
        )

    @extend_schema(
        tags=["Уведомления"],
        summary="События (лента)",
        description=(
            "Список сохранённых уведомлений. Push в реальном времени: WebSocket "
            "`/ws/notifications/?token=<JWT_access>` (тот же токен, что для API)."
        ),
    )
    def get(self, request):
        _ensure_reminder_children(request.user)
        qs = NotificationEvent.objects.filter(recipient=request.user).order_by("-created_at")[:200]
        return Response(
            [
                {
                    "id": x.id,
                    "kind": x.kind,
                    "title": x.title,
                    "body": x.body,
                    "link_url": x.link_url,
                    "read_at": x.read_at,
                    "event_at": x.event_at,
                    "notify_at": getattr(x, "notify_at", None),
                    "parent_id": getattr(x, "parent_id", None),
                    "subject_user_id": x.subject_user_id,
                    "subject_user_label": x.subject_user_label,
                    "created_at": x.created_at,
                }
                for x in qs
            ]
        )

    @extend_schema(
        tags=["Уведомления"],
        summary="Создать напоминание / событие",
        request=NotificationEventCreateSerializer,
        responses={
            201: inline_serializer(
                name="NotificationEventCreated",
                fields={"id": serializers.IntegerField()},
            ),
        },
    )
    def post(self, request):
        title = (request.data.get("title") or "").strip() or "Напоминание"
        body = (request.data.get("body") or "").strip()
        event_at = request.data.get("event_at")
        subject_user_id = request.data.get("subject_user_id")
        label = (request.data.get("subject_user_label") or "").strip()

        subj = None
        if subject_user_id not in (None, "", 0, "0"):
            try:
                sid = int(subject_user_id)
            except (TypeError, ValueError):
                sid = 0
            if sid:
                allowed_ids = {request.user.id}
                allowed_ids.update(FamilyLink.objects.filter(owner=request.user).values_list("member_id", flat=True))
                if sid not in allowed_ids:
                    return Response({"detail": "Недопустимый subject_user_id."}, status=status.HTTP_400_BAD_REQUEST)
                subj = CustomUser.objects.filter(id=sid).first()

        ev = NotificationEvent.objects.create(
            recipient=request.user,
            kind=NotificationEvent.Kind.REMINDER,
            title=title,
            body=body,
            event_at=event_at,
            subject_user=subj,
            subject_user_label=label,
        )
        return Response({"id": ev.id}, status=status.HTTP_201_CREATED)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Уведомления"],
        summary="Отметить событие прочитанным",
        description="Тело запроса не требуется.",
        request=inline_serializer(name="NotificationMarkReadEmptyBody", fields={}),
        responses={200: inline_serializer(name="NotificationMarkReadOk", fields={"ok": serializers.BooleanField()})},
    )
    def post(self, request, pk: int):
        n = NotificationEvent.objects.filter(pk=pk, recipient=request.user).first()
        if not n:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
        return Response({"ok": True})


class NotificationBadgeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Уведомления"],
        summary="Счётчики для колокольчика (badge)",
        description=(
            "Возвращает количество непрочитанных событий и непросмотренного «Полезного», "
            "а также рекомендуемую вкладку для открытия (если unread есть в обоих — «events»)."
        ),
        responses={
            200: inline_serializer(
                name="NotificationBadge",
                fields={
                    "events_unread": serializers.IntegerField(),
                    "events_unread_today": serializers.IntegerField(),
                    "useful_unread": serializers.IntegerField(),
                    "open_tab": serializers.ChoiceField(choices=["events", "useful", "none"]),
                },
            )
        },
    )
    def get(self, request):
        _ensure_reminder_children(request.user)
        now = timezone.now()
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        qs = NotificationEvent.objects.filter(recipient=request.user)
        events_unread = qs.filter(read_at__isnull=True).count()
        events_unread_today = qs.filter(read_at__isnull=True, created_at__gte=start_today).count()

        seen = UsefulFeedSeen.objects.filter(user=request.user).first()
        last_seen = seen.last_seen_at if seen else None

        useful_unread = 0
        if last_seen:
            upd_max = AppUpdateBroadcast.objects.aggregate(mx=Max("published_at"))["mx"]
            if upd_max and upd_max > last_seen:
                useful_unread += 1
            if request.user.useful_tips_subscribed:
                if UsefulTip.objects.filter(is_active=True, updated_at__gt=last_seen).exists():
                    useful_unread += 1
        else:
            if AppUpdateBroadcast.objects.exists():
                useful_unread += 1
            if request.user.useful_tips_subscribed and UsefulTip.objects.filter(is_active=True).exists():
                useful_unread += 1

        open_tab = "none"
        if events_unread:
            open_tab = "events"
        elif useful_unread:
            open_tab = "useful"

        return Response(
            {
                "events_unread": events_unread,
                "events_unread_today": events_unread_today,
                "useful_unread": useful_unread,
                "open_tab": open_tab,
            }
        )


# --- Support ---
class FeedbackCreateView(APIView):
    permission_classes = [IsAuthenticated]

    class FeedbackCreateSerializer(serializers.Serializer):
        message = serializers.CharField(
            max_length=8000,
            help_text="Текст письма (поле «Письмо» / «Сообщение»).",
        )
        email = serializers.EmailField(
            required=True,
            help_text="Почта обратной связи — куда можно ответить пользователю.",
        )
        subject = serializers.CharField(
            max_length=255,
            required=False,
            allow_blank=True,
            help_text="Тема (необязательно). По умолчанию «Обратная связь».",
        )

    @extend_schema(
        tags=["Поддержка"],
        summary="Отправить обратную связь",
        description=(
            "Сохраняет обращение в БД и отправляет письмо на `FEEDBACK_TO_EMAIL` "
            "(по умолчанию cybertime.syst@gmail.com).\n\n"
            "Кнопка в UI: **Отправить** (не «Сохранить»).\n"
            "Обязательные поля: `email` (Почта обратной связи), `message` (Письмо)."
        ),
        request=FeedbackCreateSerializer,
        responses={
            201: inline_serializer(
                name="FeedbackOk",
                fields={
                    "ok": serializers.BooleanField(),
                    "detail": serializers.CharField(),
                    "ticket_id": serializers.IntegerField(),
                },
            )
        },
    )
    def post(self, request):
        s = self.FeedbackCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ticket = FeedbackTicket.objects.create(
            user=request.user,
            email=(s.validated_data.get("email") or "").strip(),
            subject=(s.validated_data.get("subject") or "").strip() or "Обратная связь",
            message=s.validated_data["message"].strip(),
        )
        return Response(
            {
                "ok": True,
                "detail": "Сообщение отправлено.",
                "ticket_id": ticket.id,
            },
            status=status.HTTP_201_CREATED,
        )


class PsychologyInquiryView(APIView):
    permission_classes = [IsAuthenticated]

    class PsychologyInquirySerializer(serializers.Serializer):
        message = serializers.CharField(max_length=8000)

    @extend_schema(
        tags=["Поддержка"],
        summary="Вопрос психологу",
        description="Сообщение сохраняется и отправляется на почту психолога (адрес из настроек сервера).",
        request=PsychologyInquirySerializer,
        responses={201: inline_serializer(name="PsychologyInquiryOk", fields={"ok": serializers.BooleanField()})},
    )
    def post(self, request):
        s = self.PsychologyInquirySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        PsychologyInquiry.objects.create(user=request.user, message=s.validated_data["message"])
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


class ChatThreadListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Поддержка"], summary="Чаты поддержки")
    def get(self, request):
        qs = ChatThread.objects.filter(user=request.user).order_by("-updated_at")[:50]
        return Response([{"id": t.id, "title": t.title, "status": t.status, "updated_at": t.updated_at} for t in qs])

    @extend_schema(
        tags=["Поддержка"],
        summary="Создать чат",
        request=inline_serializer(
            name="ChatThreadCreateRequest",
            fields={
                "title": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    max_length=255,
                    help_text="Заголовок треда; по умолчанию «Поддержка».",
                ),
            },
        ),
        responses={
            201: inline_serializer(
                name="ChatThreadCreated",
                fields={"id": serializers.IntegerField(), "title": serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        title = (request.data.get("title") or "Поддержка").strip()[:255]
        t = ChatThread.objects.create(user=request.user, title=title)
        return Response({"id": t.id, "title": t.title}, status=status.HTTP_201_CREATED)


class ChatMessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Поддержка"], summary="Сообщения в чате")
    def get(self, request, thread_id: int):
        t = ChatThread.objects.filter(pk=thread_id, user=request.user).first()
        if not t:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        msgs = t.messages.order_by("created_at")[:500]
        return Response(
            [
                {
                    "id": m.id,
                    "body": m.body,
                    "is_staff": m.is_staff,
                    "created_at": m.created_at,
                    "sender_id": m.sender_id,
                }
                for m in msgs
            ]
        )

    @extend_schema(
        tags=["Поддержка"],
        summary="Отправить сообщение",
        request=inline_serializer(
            name="ChatMessageCreateRequest",
            fields={"body": serializers.CharField(help_text="Текст сообщения.")},
        ),
        responses={
            201: inline_serializer(
                name="ChatMessageCreated",
                fields={"id": serializers.IntegerField(), "created_at": serializers.DateTimeField()},
            ),
        },
    )
    def post(self, request, thread_id: int):
        t = ChatThread.objects.filter(pk=thread_id, user=request.user).first()
        if not t:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "body обязательно."}, status=status.HTTP_400_BAD_REQUEST)
        m = ChatMessage.objects.create(thread=t, sender=request.user, is_staff=False, body=body)
        t.save(update_fields=["updated_at"])
        return Response({"id": m.id, "created_at": m.created_at}, status=status.HTTP_201_CREATED)


# --- Drugs: reviews, stars, discuss, analogs ---
class DrugReviewListCreateView(APIView):
    permission_classes = [AllowAny]

    class DrugReviewCreateSerializer(serializers.Serializer):
        rating = serializers.IntegerField(min_value=1, max_value=5)
        text = serializers.CharField(max_length=4000)

    @extend_schema(tags=["Отзывы на лекарства"], summary="Одобренные отзывы на лекарство")
    def get(self, request, drug_id: int):
        qs = DrugReview.objects.filter(drug_id=drug_id, status=DrugReview.Status.APPROVED).order_by("-created_at")[:100]
        return Response(
            [
                {
                    "id": r.id,
                    "rating": r.rating,
                    "text": r.text,
                    "created_at": r.created_at,
                    "author": r.user.get_full_name() or r.user.username,
                }
                for r in qs
            ]
        )

    @extend_schema(
        tags=["Отзывы на лекарства"],
        summary="Добавить отзыв (на модерацию)",
        request=DrugReviewCreateSerializer,
        responses={
            201: inline_serializer(
                name="DrugReviewPending",
                fields={
                    "ok": serializers.BooleanField(),
                    "status": serializers.CharField(),
                },
            ),
        },
    )
    def post(self, request, drug_id: int):
        if not request.user.is_authenticated:
            return Response({"detail": "Требуется авторизация."}, status=status.HTTP_401_UNAUTHORIZED)
        if not Drug.objects.filter(pk=drug_id).exists():
            return Response({"detail": "Лекарство не найдено."}, status=status.HTTP_404_NOT_FOUND)
        s = self.DrugReviewCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        text = s.validated_data["text"]
        if contains_profanity(text):
            return Response({"detail": "Отклонено: содержит мат.", "reason": "Содержит мат"}, status=status.HTTP_400_BAD_REQUEST)
        DrugReview.objects.create(
            drug_id=drug_id,
            user=request.user,
            rating=s.validated_data["rating"],
            text=text,
            status=DrugReview.Status.PENDING,
        )
        return Response({"ok": True, "status": "pending"}, status=status.HTTP_201_CREATED)


class DrugStarRatingView(APIView):
    permission_classes = [IsAuthenticated]

    class DrugStarRatingSerializer(serializers.Serializer):
        stars = serializers.IntegerField(min_value=1, max_value=5)

    @extend_schema(
        tags=["Оценки лекарств"],
        summary="Оценка звёздами (не чаще 1 раза в 24ч)",
        request=DrugStarRatingSerializer,
        responses={200: DrugSerializer},
    )
    def post(self, request, drug_id: int):
        if not Drug.objects.filter(pk=drug_id).exists():
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        s = self.DrugStarRatingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = DrugUserStarRating.objects.filter(drug_id=drug_id, user=request.user).first()
        if obj and (timezone.now() - obj.updated_at) < timedelta(hours=24):
            return Response({"detail": "Менять оценку можно раз в 24 часа."}, status=status.HTTP_400_BAD_REQUEST)
        DrugUserStarRating.objects.update_or_create(
            drug_id=drug_id,
            user=request.user,
            defaults={"stars": s.validated_data["stars"]},
        )
        drug = Drug.objects.get(pk=drug_id)
        return Response(DrugSerializer(drug, context={"request": request}).data)


class DrugDiscussionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Обсуждения лекарств"], summary="Обсуждение лекарства — список сообщений")
    def get(self, request, drug_id: int):
        if not Drug.objects.filter(pk=drug_id).exists():
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        th, _ = DrugDiscussionThread.objects.get_or_create(drug_id=drug_id)
        posts = th.posts.select_related("user").order_by("created_at")[:500]
        return Response(
            {
                "drug_id": drug_id,
                "items": [
                    {
                        "id": p.id,
                        "body": p.body,
                        "created_at": p.created_at,
                        "user": {
                            "id": p.user_id,
                            "name": p.user.get_full_name() or p.user.username,
                            "avatar": p.user.avatar.url if p.user.avatar else None,
                        },
                    }
                    for p in posts
                ],
            }
        )

    @extend_schema(
        tags=["Обсуждения лекарств"],
        summary="Написать в обсуждение",
        request=inline_serializer(
            name="DrugDiscussionPostRequest",
            fields={"body": serializers.CharField(help_text="Текст сообщения в треде.")},
        ),
        responses={
            201: inline_serializer(
                name="DrugDiscussionPostResponse",
                fields={"id": serializers.IntegerField(), "created_at": serializers.DateTimeField()},
            ),
        },
    )
    def post(self, request, drug_id: int):
        if not Drug.objects.filter(pk=drug_id).exists():
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "body обязательно."}, status=status.HTTP_400_BAD_REQUEST)
        th, _ = DrugDiscussionThread.objects.get_or_create(drug_id=drug_id)
        p = DiscussionPost.objects.create(thread=th, user=request.user, body=body)
        return Response({"id": p.id, "created_at": p.created_at}, status=status.HTTP_201_CREATED)


class DrugAnalogListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Аналоги лекарств"], summary="Аналоги (данные из БД; парсер заполняет)")
    def get(self, request, drug_id: int):
        rows = DrugAnalog.objects.filter(drug_id=drug_id)[:100]
        return Response([{"id": r.id, "name": r.name, "price": str(r.price) if r.price is not None else None} for r in rows])


# --- FAQ, Survey ---
class FaqSearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Помощник"],
        summary="FAQ: список всех вопросов или поиск по вопрос/ответ",
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=False,
                description="Поиск по вопросу или ответу. Если не передан — возвращаются все активные FAQ.",
            ),
        ],
    )
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        qs = FaqItem.objects.filter(is_active=True).order_by("id")
        if q:
            qs = qs.filter(Q(question__icontains=q) | Q(answer__icontains=q))
        return Response([{"id": x.id, "question": x.question, "answer": x.answer[:2000]} for x in qs[:100]])


# --- Admin analytics (TZ §5.1 / §8.2.4) ---
class AdminSummaryView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Администрирование"],
        summary="Сводка по пользователям и городам",
        description="Доступно только пользователям с флагом is_staff (администратор Django).",
    )
    def get(self, request):
        rows = (
            User.objects.exclude(city="")
            .values("city")
            .annotate(c=Count("id"))
            .order_by("-c")[:200]
        )
        return Response({"users_by_city": list(rows)})


class VoiceTranscribeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Голос"],
        summary="Распознавание речи (заглушка)",
        description="Принимает аудиофайл; при необходимости подключите внешний STT или расширьте интеграцию на сервере.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "audio": {"type": "string", "format": "binary", "description": "Аудиофайл записи."},
                    "field": {
                        "type": "string",
                        "description": "Имя поля формы на клиенте (логирование/контекст).",
                    },
                },
                "required": ["audio"],
            },
        },
        responses={
            501: inline_serializer(
                name="VoiceTranscribeStub",
                fields={
                    "text": serializers.CharField(),
                    "field": serializers.CharField(),
                    "detail": serializers.CharField(),
                },
            ),
        },
    )
    def post(self, request):
        if not request.FILES.get("audio"):
            return Response({"detail": "Поле audio обязательно."}, status=status.HTTP_400_BAD_REQUEST)
        field = (request.data.get("field") or "").strip() or "unknown"
        return Response(
            {
                "text": "",
                "field": field,
                "detail": "Подключите внешний STT или расширьте apps.core.gemini для аудио.",
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
