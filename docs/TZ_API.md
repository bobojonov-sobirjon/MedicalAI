# MedicAI — backend API по ТЗ (обзор)

Документация OpenAPI: `/docs/`. Префикс всех методов: `/api/`.

## Защита API (ТЗ §3.3)

- Опционально: переменные `BACKEND_API_KEY`, `REQUIRE_BACKEND_API_KEY=true` — тогда для всех `/api/*` нужен заголовок **`X-Backend-Key`**.

## Уже было (этап 1 + ранее)

- Авторизация, профиль, JWT, соцсети, сброс пароля.
- Справочник заболеваний/лекарств, история болезней, вложенные визиты/анализы/рецепты.
- Ассистент `POST assistant/diagnose/` (Gemini + справочник + **FAQ** из БД).
- Аптечка, OCR анализов, недавние просмотры лекарств.

## Новое по разделам ТЗ

### §7.9 — Справочник заболеваний (карточка с лекарствами)

- `GET /api/catalog/diseases/<id>/` — в ответе блок **`drugs`** (рекомендуемые препараты).

### §7.11 — Помощник (симптомы, части тела)

- `GET /api/catalog/symptoms/?q=` — автодополнение симптомов.
- `GET /api/catalog/body-parts/` — части тела для UI.

### §7.12 — Уведомления

- `GET/POST /api/me/notifications/events/` — лента событий / создать напоминание.
- `POST /api/me/notifications/events/<id>/read/` — прочитано.
- `GET /api/me/notifications/useful/` — «Полезное» + обновления программы (советы только при подписке).
- `GET/PATCH /api/me/tip-settings/` — лимит советов в сутки, подписка.
- `POST/DELETE /api/me/disease-tip-subscribe/<disease_id>/` — советы по болезни.

### §7.13 — Мед. учреждения

- `GET /api/geo/cities/`
- `GET /api/geo/facilities/?kind=pharmacy|hospital&city_id=&q=`
- `GET /api/geo/facilities/<id>/`

*(Наполнение: админка; импорт из Яндекс/2GIS — отдельный скрипт/задача.)*

### §7.14 — Моя аптечка

- Без изменения URL; при распознавании, если лекарства нет в БД, **создаётся** карточка `Drug` с фото (ТЗ).

### §7.15–7.16 — О компании, конфиденциальность

- `GET /api/content/pages/<slug>/` — slug задаётся в админке (`StaticPage`), например `about`, `privacy`.

### §7.17 — Обратная связь, чат

- `POST /api/support/feedback/` — письмо в БД (отправка на почту — при настроенном SMTP).
- `POST /api/support/psychology/` — вопрос психологу → письмо на `PSYCHOLOGY_EMAIL` (по умолчанию `psychology@medic-ai.ru`).
- `GET/POST /api/me/chat/threads/`, `GET/POST /api/me/chat/threads/<id>/messages/` — REST-чат (WebSocket позже).

### §7.10.1–7.10.2 — Отзывы и оценки

- `GET/POST /api/catalog/drugs/<id>/reviews/` — список одобренных / новый отзыв (**модерация**, фильтр мата).
- `POST /api/catalog/drugs/<id>/star-rating/` — звёзды (**не чаще 1 раза в 24 ч**), пересчёт среднего `Drug.rating`.
- `GET/POST /api/catalog/drugs/<id>/discussion/` — обсуждение.
- `GET /api/catalog/drugs/<id>/analogs/` — аналоги из БД (парсер заполняет `DrugAnalog`).

### §7.21 — Релакс

- `GET /api/relax/feed/?category=gif|video`

### §6.1 — Вопрос/ответ

- `GET /api/faq/?q=` — поиск по `FaqItem` (также подмешивается в `assistant/diagnose`).

### §7.7 / §8.2.3 — Несколько профилей

- `GET|POST /api/me/profiles/` — список (я + доп. профили) и «Добавить пользователя».
- `GET|PUT|PATCH|DELETE /api/me/profiles/<profile_id>/` — карточка, правка, удаление доп. профиля.
- `GET|PATCH /api/auth/me/` — свой ЛК (владелец).
- В истории болезней: поле **`subject_user_id`** — для кого запись (сам или доп. профиль).

### Прочее

- `GET /api/content/config/` — `free_trial_months`, `psychology_email`.
- `POST /api/me/survey/` — опрос (JSON `answers`, `slug`, `comment`).
- `POST /api/me/voice/transcribe/` — заглушка STT (ТЗ §8.2.2 — подключите сервис).
- `GET /api/admin/metrics/summary/` — **только staff**: пользователи по городам.

### Профиль (доп. поля ТЗ §8.2.2)

- `PATCH /api/auth/me/` — `chronic_diseases`, `had_covid`, `useful_tips_subscribed`, `nickname`, **`pin_code`** (4–8 цифр, хранится как хэш).

## Частично / вне backend в этом репозитории

- **Обучение своей НН на сервере**, выделение GPU, пайплайн без утечки ПДн (ТЗ §3.10, §6.1, §8.2.2) — требуется отдельный ML-сервис.
- **Парсеры** Vidal/Zhivika, **AppMetrica**, **SMS-регистрация по телефону**, **эквайринг**, **push по расписанию** (за 24ч/3ч/1ч) — Celery/FCM и внешние ключи.
- **Полное логирование** ТЗ §3.9 в БД (все действия, медленные запросы, 1 год хранения) — заложены модели `AuditLogEntry`, `ApiErrorLog`, `SearchQueryLog`; middleware записи можно донастроить.
- **Выгрузка XLS аналитики** (§5.1) — endpoint можно добавить к `admin/metrics`.
- **Релакс / советы из Google Docs** — сейчас ручное управление в админке.
