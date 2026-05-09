# MedicAI — Stage 2 API для Mobile Frontend (REST + JWT)

Документ описывает API **этапа 2** (ядро продукта): **AI‑ассистент**, **OCR анализов**, **история болезней** + связанные разделы, которые уже реализованы в бэкенде (справочники, аптечка, уведомления, поддержка и т.д.).  
Формат документа — для **мобильных разработчиков**: точные URL, параметры, типы, обязательность, примеры запросов/ответов.

---

## Общая информация

- **Проект**: MedicAI (Django + Django REST Framework)
- **Базовый префикс API**: `/api/`
- **Формат данных**: `application/json; charset=utf-8`  
  Исключения: загрузка файлов — `multipart/form-data`
- **Документация Swagger**: `/docs/` (OpenAPI schema: `/schema/`)

### Base URL

Укажите один из вариантов (пример):

- **DEV**: `http://127.0.0.1:8000`
- **STAGING**: `https://staging.example.com`
- **PROD**: `http://85.198.101.179:8007/`

---

## Аутентификация (JWT) — обязательно

### Заголовок для защищённых методов

Все методы, помеченные как **JWT**, требуют:

`Authorization: Bearer <access_token>`

### Опционально: глобальный API‑ключ (ТЗ §3.3)

Если на сервере включено требование ключа, добавляйте заголовок:

`X-Backend-Key: <ключ>`

---

## JWT FLOW (пример для клиента)

### 1) Регистрация

- **METHOD**: `POST`
- **URL**: `/api/auth/register/`
- **AUTH**: нет
- **Content-Type**: `application/json`

**Body (JSON):**

- `email`: string (**required**, уникальный)
- `username`: string (**required**, уникальный)
- `password`: string (**required**, min 6, минимум 1 буква и 1 цифра)
- `phone_number`: string (optional, уникальный если указан)
- `first_name`: string (optional)
- `last_name`: string (optional)

**Example request:**

```json
{
  "email": "user@example.com",
  "username": "user123",
  "password": "Secret123",
  "phone_number": "+79990000000",
  "first_name": "Иван",
  "last_name": "Иванов"
}
```

**Response 201:**

```json
{
  "user": {
    "id": 6,
    "username": "user123",
    "email": "user@example.com",
    "phone_number": "+79990000000",
    "nickname": "",
    "first_name": "Иван",
    "last_name": "Иванов",
    "avatar": null,
    "gender": "",
    "city": "",
    "date_of_birth": null,
    "height_cm": null,
    "weight_kg": null,
    "chronic_diseases": "",
    "had_covid": null,
    "useful_tips_subscribed": false
  },
  "tokens": {
    "access": "jwt_access_token",
    "refresh": "jwt_refresh_token"
  }
}
```

### 2) Логин

- **METHOD**: `POST`
- **URL**: `/api/auth/login/`
- **AUTH**: нет

**Body (JSON):**

- `identifier`: string (**required**) — `username` или `email` или `phone_number`
- `password`: string (**required**)

**Example request:**

```json
{
  "identifier": "user@example.com",
  "password": "Secret123"
}
```

**Response 200:**

```json
{
  "user": { "id": 6, "username": "user123", "email": "user@example.com" },
  "tokens": { "access": "jwt_access_token", "refresh": "jwt_refresh_token" }
}
```

### 3) Обновить access по refresh

- **METHOD**: `POST`
- **URL**: `/api/auth/refresh/`
- **AUTH**: нет

**Body (JSON):**

- `refresh`: string (**required**)

**Response 200:**

```json
{ "access": "new_jwt_access_token" }
```

### 4) Профиль (прочитать / обновить)

- **METHOD**: `GET`
- **URL**: `/api/auth/me/`
- **AUTH**: JWT

- **METHOD**: `PATCH`
- **URL**: `/api/auth/me/`
- **AUTH**: JWT

**PATCH Body (JSON или multipart):** любое подмножество полей:

- `first_name`: string (optional)
- `last_name`: string (optional)
- `nickname`: string (optional)
- `avatar`: file (optional, **multipart**)
- `phone_number`: string (optional)
- `username`: string (optional, уникальный)
- `gender`: string (optional) — `male|female|other`
- `city`: string (optional)
- `date_of_birth`: string (optional) — `YYYY-MM-DD`
- `height_cm`: integer (optional)
- `weight_kg`: number (optional)
- `chronic_diseases`: string (optional)
- `had_covid`: boolean|null (optional)
- `useful_tips_subscribed`: boolean (optional)
- `pin_code`: string (optional) — 4–8 цифр, сохраняется как хэш

---

## ЯДРО Stage 2 (то, что относится к «главной ценности продукта»)

### A) AI‑Ассистент (диагностика по симптомам)

#### POST `/api/assistant/diagnose/` (JWT)

- **METHOD**: `POST`
- **AUTH**: JWT
- **Content-Type**: `application/json`

**Body (JSON):**

- `symptoms`: integer[] (**required**) — список `Symptom.id` из `GET /api/catalog/symptoms/?q=...`
- `symptoms_text`: string (optional) — доп. симптомы/уточнения текстом (если нет в справочнике)
- `body_parts`: integer[] (optional, default `[]`) — список `BodyPart.id` из `GET /api/catalog/body-parts/`
- `temperature_c`: number|null (optional)
- `blood_pressure`: string (optional)

**Example request:**

```json
{
  "symptoms": [1, 9],
  "symptoms_text": "",
  "body_parts": [1],
  "temperature_c": 37.5,
  "blood_pressure": "120/80"
}
```

**Response 200 (структура):**

```json
{
  "diagnosis_id": 1,
  "symptoms_resolved": [
    { "id": 1, "name": "Головная боль", "aliases": "..." }
  ],
  "body_parts_resolved": [
    { "id": 1, "code": "head", "label": "Голова" }
  ],
  "catalog_candidates": [{ "id": 53, "name": "…", "description": "…" }],
  "faq_hits": [{ "id": 1, "question": "…", "answer": "…" }],
  "catalog_matched": [{ "id": 53, "name": "…", "description": "…" }],
  "ai": {
    "summary": "…",
    "possible_conditions": [
      { "name": "…", "rationale": "…", "urgency": "routine" }
    ],
    "suggested_next_steps": ["…"],
    "disclaimer": "…"
  }
}
```

> Примечание: если AI‑провайдер недоступен или нет баланса (например RuTronix 402), поле `ai` возвращается с безопасным fallback‑текстом, а совпадения берутся из справочника/FAQ.

#### GET `/api/assistant/diagnoses/` (JWT)

- **METHOD**: `GET`
- **AUTH**: JWT

Возвращает историю запросов помощника **только текущего пользователя** (последние 200).

**Response 200 (пример):**

```json
[
  {
    "id": 1,
    "symptom_ids": [1],
    "symptoms": [{ "id": 1, "name": "Головная боль", "aliases": "..." }],
    "symptoms_text": "",
    "body_part_ids": [1],
    "body_parts": [{ "id": 1, "code": "head", "label": "Голова" }],
    "temperature_c": 37.5,
    "blood_pressure": "120/80",
    "symptoms_resolved": [{ "id": 1, "name": "Головная боль", "aliases": "..." }],
    "body_parts_resolved": [{ "id": 1, "code": "head", "label": "Голова" }],
    "catalog_candidates": [],
    "faq_hits": [],
    "catalog_matched": [],
    "result": { "ai": { "summary": "..." } },
    "created_at": "2026-05-08T17:35:37.216596Z"
  }
]
```

#### GET `/api/assistant/diagnoses/<id>/` (JWT)

- **METHOD**: `GET`
- **AUTH**: JWT

Детали одного сохранённого результата. Если `id` не принадлежит текущему пользователю — `404`.

---

### B) OCR анализов (распознавание по фото)

#### 1) Загрузить/обновить анализ с фото (JWT)

- **METHOD**: `PATCH`
- **URL**: `/api/me/analyses/<id>/`
- **AUTH**: JWT
- **Content-Type**: `multipart/form-data` (для поля `photo`)

**Fields (multipart):**

- `taken_date`: string (optional) `YYYY-MM-DD`
- `name`: string (optional)
- `result_text`: string (optional)
- `photo`: file (optional) — фото анализа

#### 2) Запустить OCR (JWT)

- **METHOD**: `POST`
- **URL**: `/api/me/analyses/<id>/ocr/`
- **AUTH**: JWT

**Query params:**

- `mode`: string (optional, default `append`)
  - `append` — дописать в `result_text`
  - `replace` — заменить `result_text` целиком

**Body:** пустой `{}`.

**Response 200:** объект анализа (как `GET/PATCH /api/me/analyses/<id>/`), где `result_text` обновлён.

**Response 400:** если у анализа нет `photo`.

---

### C) История болезней (медкарта пользователя)

#### 1) CRUD записей (JWT)

- **GET** `/api/me/disease-records/` — список  
  Query: `q` (optional) поиск по заголовку/симптомам/названию болезни
- **POST** `/api/me/disease-records/` — создать
- **GET** `/api/me/disease-records/<id>/` — детали
- **PATCH** `/api/me/disease-records/<id>/` — обновить
- **DELETE** `/api/me/disease-records/<id>/` — удалить

**Body для POST/PATCH (`DiseaseRecordUpsertSerializer`):**

- `date_of_illness`: string (optional) `YYYY-MM-DD`
- `title`: string (optional)
- `symptoms`: string (optional)
- `disease_id`: integer|null (optional) — связь со справочником болезней
- `subject_user_id`: integer|null (optional) — “для кого” (я или член семьи)
- `drug_ids`: integer[] (optional) — лекарства из справочника
- `doctor_visits`: object[] (optional) — если передан, **заменяет** текущий список
- `analyses`: object[] (optional) — если передан, **заменяет** текущий список
- `prescriptions`: object[] (optional) — если передан, **заменяет** текущий список

**Пример POST:**

```json
{
  "date_of_illness": "2026-01-01",
  "title": "ОРВИ",
  "symptoms": "кашель, температура",
  "disease_id": 53,
  "subject_user_id": null,
  "drug_ids": [18],
  "doctor_visits": [
    {
      "visit_date": "2026-01-02",
      "specialty": "Терапевт",
      "doctor_full_name": "Иванова А.А.",
      "diagnosis": "…",
      "medicines_text": "…",
      "procedures_text": "…"
    }
  ],
  "analyses": [
    { "taken_date": "2026-01-03", "name": "ОАК", "result_text": "…", "photo": null }
  ],
  "prescriptions": [
    { "photo": null, "note": "…" }
  ]
}
```

#### 2) Визиты врача (JWT)

- **GET/POST** `/api/me/disease-records/<record_id>/doctor-visits/`
- **GET/PATCH/DELETE** `/api/me/doctor-visits/<id>/`

**POST/PATCH body:**

- `visit_date`: string `YYYY-MM-DD` (optional)
- `specialty`: string (optional)
- `doctor_full_name`: string (optional)
- `diagnosis`: string (optional)
- `medicines_text`: string (optional)
- `procedures_text`: string (optional)

#### 3) Анализы (JWT)

- **GET/POST** `/api/me/disease-records/<record_id>/analyses/`
- **GET/PATCH/DELETE** `/api/me/analyses/<id>/`
- OCR: `POST /api/me/analyses/<id>/ocr/` (см. выше)

#### 4) Рецепты/фото (JWT)

- **GET/POST** `/api/me/disease-records/<record_id>/prescriptions/`
- **GET/PATCH/DELETE** `/api/me/prescriptions/<id>/`

Body (POST/PATCH):

- `photo`: file|null (optional; для загрузки — multipart)
- `note`: string (optional)

---

## Остальные реализованные разделы (для Stage 2 UI)

### 1) Справочник заболеваний (public)

- **GET** `/api/catalog/diseases/?q=<строка>` (optional q)
- **GET** `/api/catalog/diseases/<id>/`

### 2) Справочник лекарств (public + частично JWT)

- **GET** `/api/catalog/drugs/?q=<строка>` (optional q)
- **GET** `/api/catalog/drugs/<id>/`

**Недавние (JWT):**

- **GET** `/api/me/recent-drugs/?limit=30` (limit optional, default 30, max 100)
- **POST** `/api/catalog/drugs/<id>/view/` (body `{}`) — записать просмотр

**Отзывы/оценки/обсуждение/аналоги:**

- **GET** `/api/catalog/drugs/<drug_id>/reviews/` (public)
- **POST** `/api/catalog/drugs/<drug_id>/reviews/` (JWT) body: `{ rating: 1..5, text: string }` → 201 pending
- **POST** `/api/catalog/drugs/<drug_id>/star-rating/` (JWT) body: `{ stars: 1..5 }`
- **GET** `/api/catalog/drugs/<drug_id>/discussion/` (JWT)
- **POST** `/api/catalog/drugs/<drug_id>/discussion/` (JWT) body: `{ body: string }`
- **GET** `/api/catalog/drugs/<drug_id>/analogs/` (public)

### 3) Помощник — справочники UI (public)

- **GET** `/api/catalog/body-parts/`
- **GET** `/api/catalog/symptoms/?q=<строка>` (**q required**)
- **GET** `/api/faq/?q=<строка>` (public, q min 2 символа)

### 4) Уведомления (JWT)

- **GET** `/api/me/notifications/useful/` — вкладка «Полезное» (советы + обновления)
- **POST** `/api/me/notifications/useful/seen/` body `{}` → `{ ok: true }` (отметить «Полезное» просмотренным, для колокольчика)
- **GET** `/api/me/tip-settings/`
- **PATCH** `/api/me/tip-settings/` body: `{ tips_per_day?: 1..20, useful_subscribed?: boolean }`
- **POST** `/api/me/disease-tip-subscribe/<disease_id>/` body `{}` → `{ ok: true }`
- **DELETE** `/api/me/disease-tip-subscribe/<disease_id>/` → 204
- **GET** `/api/me/notifications/events/`
- **POST** `/api/me/notifications/events/` body: `{ title?, body?, event_at?: datetime|null, subject_user_id?: int|null, subject_user_label? }` → `{ id }`
- **POST** `/api/me/notifications/events/<id>/read/` body `{}` → `{ ok: true }`
- **GET** `/api/me/notifications/badge/` → `{ events_unread, events_unread_today, useful_unread, open_tab }` (badge колокольчика)

### 5) Медучреждения (public)

- **GET** `/api/geo/cities/?q=<строка>&limit=200` (q optional, limit optional)
- **GET** `/api/geo/facilities/?kind=pharmacy|hospital&city_id=<int>&q=<string>`
- **GET** `/api/geo/facilities/<id>/`

### 6) Моя аптечка (JWT)

- **GET/POST** `/api/me/cabinet/items/?q=<строка>` (q optional)
- **GET/PATCH/DELETE** `/api/me/cabinet/items/<id>/`

Body для POST/PATCH (`CabinetItemSerializer`):

- `drug`: integer (optional) — id из справочника
- `custom_name`: string (optional) — если нет `drug`
- `expires_at`: string|null (optional) — дата/время (ISO)
- `note`: string (optional)
- `photo`: file (optional, multipart)

**Распознавание по фото (JWT):**

- **POST** `/api/me/cabinet/recognize/` (**multipart**)
  - `image`: file (required)

### 7) Поддержка (JWT)

- **POST** `/api/support/feedback/` body:
  - `message`: string (required)
  - `subject`: string (optional)
  - `email`: string (optional)

- **POST** `/api/support/psychology/` body:
  - `message`: string (required)

### 8) Чат поддержки (JWT, REST polling)

- **GET/POST** `/api/me/chat/threads/`
  - POST body: `{ title?: string }`
- **GET/POST** `/api/me/chat/threads/<thread_id>/messages/`
  - POST body: `{ body: string }`

### 9) Релакс (public)

- **GET** `/api/relax/feed/?category=gif|video`

### 10) Опрос (JWT)

- **POST** `/api/me/survey/` body:
  - `slug`: string (required)
  - `answers`: object (required, JSON)
  - `comment`: string (optional)

### 11) Голос → текст (JWT, заглушка)

- **POST** `/api/me/voice/transcribe/` (**multipart**)
  - `audio`: file (required)
  - `field`: string (optional)

Ответ текущей версии: `501 Not Implemented` с JSON `{ text, field, detail }`.

### 12) Семья (JWT)

- **GET** `/api/me/family/`
- **POST** `/api/me/family/` body: `{ member_id: int, label?: string }`
- **DELETE** `/api/me/family/<member_id>/` (body нет)

---

## Важно для Stage 2 (как в вашем тексте «ядро системы»)

**Да — этот блок реализован:**

- **AI‑ассистент**: `POST /api/assistant/diagnose/` (AI‑провайдер: Gemini или RuTronix + справочник + FAQ)
- AI‑провайдер может быть Gemini или RuTronix (единый API). При недоступности AI включается fallback по локальному справочнику/FAQ.
- **OCR анализов**: `POST /api/me/analyses/<id>/ocr/` + загрузка фото в анализ (multipart)
- **История болезней**: полный CRUD записей + вложения (визиты/анализы/рецепты) + отдельные CRUD эндпоинты

---

## Быстрый чек‑лист для интеграции на мобайле

- **JWT** храните: `access` (короткий) + `refresh` (длинный)
- При `401`:
  - попытка `POST /api/auth/refresh/`
  - повтор запроса с новым `access`
- **Файлы** (анализы, рецепты, фото для распознавания) — только `multipart/form-data`
- Для подробностей по полям/ошибкам — сверяйтесь со Swagger `/docs/`

