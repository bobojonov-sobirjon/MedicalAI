# MedicAI — API qo‘llanmasi mobil frontend dasturchilar uchun

To‘liq, ishlab chiqarish uchun mo‘ljallangan REST API hujjati.**Asos:** Django 5.x + Django REST Framework, JWT (`rest_framework_simplejwt`).

---

## 1. Umumiy ma’lumot

| Parametr | Qiymat |
|----------|--------|
| Loyiha | **MedicAI** |
| Backend | Django + Django REST Framework (DRF) |
| Format | **`Content-Type: application/json`** (fayl yuklashda `multipart/form-data`) |
| Autentifikatsiya | **JWT** — `Authorization: Bearer <access_token>` |
| API prefiksi | **`/api/`** |

### Base URL (moslamangiz bo‘yicha)

| Muhit | URL (namuna) |
|-------|----------------|
| Local dev | `http://127.0.0.1:8000` |
| Staging | `https://staging.example.com` *(sizning domeningiz)* |
| Production | `https://api.example.com` *(sizning domeningiz)* |

To‘liq manzil: `{BASE_URL}/api/...`

### Ixtiyoriy global API kaliti (TZ §3.3)

Agar serverda `REQUIRE_BACKEND_API_KEY=true` va `BACKEND_API_KEY` belgilangan bo‘lsa, **barcha** `/api/` so‘rovlarida qo‘shing:

- **Header:** `X-Backend-Key: <your_backend_key>`

---

## 2. JWT autentifikatsiya (muhim)

### 2.1 Ro‘yxatdan o‘tish (Register)

| | |
|--|--|
| **METHOD** | `POST` |
| **URL** | `/api/auth/register/` |
| **Auth** | kerak emas |

**Body (JSON)**

| Maydon | Turi | Majburiy | Tavsif |
|--------|------|----------|--------|
| `email` | `string` (email) | ha | Noyob email |
| `username` | `string` | ha | Noyob login |
| `password` | `string` | ha | Min 6 belgi; **kamida 1 harf va 1 raqam** (TZ §7.3) |
| `phone_number` | `string` \| `null` | yo‘q | Noyob bo‘lishi kerak (agar berilsa) |
| `first_name` | `string` | yo‘q | |
| `last_name` | `string` | yo‘q | |

**Misol so‘rov**

```json
{
  "email": "user@example.com",
  "username": "user123",
  "password": "secret1a",
  "first_name": "Ali",
  "last_name": "Vali"
}
```

**Javob `201 Created`**

```json
{
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com",
    "phone_number": null,
    "nickname": "",
    "first_name": "Ali",
    "last_name": "Vali",
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
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>"
  }
}
```

Mobil ilova **`tokens.access`** ni saqlaydi va keyingi himoyalangan so‘rovlar uchun ishlatadi.

---

### 2.2 Kirish (Login)

| | |
|--|--|
| **METHOD** | `POST` |
| **URL** | `/api/auth/login/` |
| **Auth** | kerak emas |

**Body (JSON)**

| Maydon | Turi | Majburiy | Tavsif |
|--------|------|----------|--------|
| `identifier` | `string` | ha | **`username`** yoki **`email`** yoki **`phone_number`** (telefon registratsiya qilingan bo‘lsa) |
| `password` | `string` | ha | Parol |

> **Eslatma:** TZ misolidagi faqat `phone` emas — loyihada **`identifier`** ishlatiladi (login / email / telefon).

**Misol**

```json
{
  "identifier": "user@example.com",
  "password": "secret1a"
}
```

**Javob `200 OK`**

```json
{
  "user": { "id": 1, "username": "user123", "email": "user@example.com", "...": "..." },
  "tokens": {
    "access": "<jwt_access_token>",
    "refresh": "<jwt_refresh_token>"
  }
}
```

---

### 2.3 Access tokenni yangilash (Refresh)

| | |
|--|--|
| **METHOD** | `POST` |
| **URL** | `/api/auth/refresh/` |
| **Auth** | kerak emas |

**Body (JSON)**

| Maydon | Turi | Majburiy |
|--------|------|----------|
| `refresh` | `string` | ha |

**Misol**

```json
{
  "refresh": "<jwt_refresh_token>"
}
```

**Javob `200 OK`**

```json
{
  "access": "<new_jwt_access_token>"
}
```

**Xato `400`:** noto‘g‘ri yoki muddati o‘tgan `refresh`.

---

### 2.4 Himoyalangan so‘rovlar

Har bir `GET/POST/PATCH/DELETE` (AllowAny bo‘lmagan endpointlar uchun):

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

Access muddati sozlamada: **`SIMPLE_JWT`** (`ACCESS_TOKEN_LIFETIME`, `REFRESH_TOKEN_LIFETIME` — `config/settings.py`).

---

## 3. Помощник (Yordamchi) — APIlar

Qo‘lda: **simptomlar ma’lumotnomasi**, **tana qismlari**, **FAQ**, **AI diagnostika (saqlanadi)**, **tarix**.

### 3.1 Simptomlar bo‘yicha qidiruv (avtoto‘ldirish)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/catalog/symptoms/` |
| **Auth** | kerak emas |

**Query parametrlar**

| Parametr | Turi | Majburiy | Tavsif |
|----------|------|----------|--------|
| `q` | `string` | shartli | Tanlangan kodda **`q` bo‘sh bo‘lsa** bo‘sh ro‘yxat `[]`; **kamida 1 belgi** berilganda qidiruv ishlaydi |

**Javob:** `Symptom` massivi — har biri: `id`, `name`, `aliases`, `created_at`, `updated_at`.

---

### 3.2 Tana qismlari (figura uchun)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/catalog/body-parts/` |
| **Auth** | kerak emas |

**Query:** yo‘q.

**Javob:** massiv — `id`, `code` (barqaror identifikator), `label`, `sort_order`, …

---

### 3.3 FAQ qidiruv (savol–javob)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/faq/` |
| **Auth** | kerak emas |

**Query parametrlar**

| Parametr | Turi | Majburiy | Tavsif |
|----------|------|----------|--------|
| `q` | `string` | ha (amalda) | 2 dan qisqa bo‘lsa server `[]` qaytaradi |

**Javob:** massiv — `id`, `question`, `answer` (qisqartirilgan, max ~2000 belgi).

---

### 3.4 Diagnostika (AI + ma’lumotnoma)

| | |
|--|--|
| **METHOD** | `POST` |
| **URL** | `/api/assistant/diagnose/` |
| **Auth** | **Bearer JWT** |

**Body (JSON)**

| Maydon | Turi | Majburiy | Default | Tavsif |
|--------|------|----------|---------|--------|
| `symptoms` | `integer[]` | ha | — | Simptom **ID**lari (`GET /api/catalog/symptoms/`); **bo‘sh bo‘lmasin** |
| `symptoms_text` | `string` | yo‘q | `""` | Qoʻshimcha matn (ma’lumotnomada yo‘q belgilar) |
| `body_parts` | `integer[]` | yo‘q | `[]` | Tana qismi **ID**lari (`GET /api/catalog/body-parts/`) |
| `temperature_c` | `number` \| `null` | yo‘q | `null` | Harorat °C |
| `blood_pressure` | `string` | yo‘q | `""` | Masalan `"120/80"` |

**Misol**

```json
{
  "symptoms": [1, 5],
  "symptoms_text": "2 kundan beri davom etmoqda",
  "body_parts": [1],
  "temperature_c": 37.2,
  "blood_pressure": "125/82"
}
```

**Javob `200`** (asosiy maydonlar): `diagnosis_id`, `symptoms_resolved`, `body_parts_resolved`, `catalog_candidates`, `catalog_matched`, `faq_hits`, `ai` (`summary`, `possible_conditions`, …). Natija bazada saqlanadi.

*(Backendda matn uchun RuTronix yoki Gemini ishlatilishi mumkin — konfiguratsiyaga bog‘liq.)*

---

### 3.5 Diagnostika tarixi (ro‘yxat)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/assistant/diagnoses/` |
| **Auth** | Bearer JWT |

Parametrlarsiz (max ~200 yozuv); faqat **joriy user**.

---

### 3.6 Diagnostika — bitta yozuv

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/assistant/diagnoses/<id>/` |
| **Auth** | Bearer JWT |

`<id>` — `diagnosis_id` yoki ro‘yxatdagi `id`.

---

## 4. Bildirishnomalar: **События** va **Полезное**

### 4.1 События (voqealar)

| METHOD | URL | Auth | Vazifa |
|--------|-----|------|--------|
| `GET` | `/api/me/notifications/events/` | JWT | Hodisalar (yangi→eski), max ~200 |
| `POST` | `/api/me/notifications/events/` | JWT | Eslatma / hodisa yaratish |
| `POST` | `/api/me/notifications/events/<pk>/read/` | JWT | O‘qilgan deb belgilash (telo ixtiyoriy/bo‘sh) |

**`POST /api/me/notifications/events/` body (JSON)**

| Maydon | Turi | Majburiy | Default | Tavsif |
|--------|------|----------|---------|--------|
| `title` | `string` | yo‘q | `"Напоминание"` | Sarlavha |
| `body` | `string` | yo‘q | `""` | Matn |
| `event_at` | `string` (ISO 8601) \| `null` | yo‘q | `null` | Voqea vaqti |
| `subject_user_id` | `integer` \| `null` | yo‘q | — | Oilaviy profil **user id** (faqat o‘z profilingiz yoki `FamilyLink` orqali bog‘langanlar) |
| `subject_user_label` | `string` | yo‘q | `""` | Masalan „Onam“ |

**`201` javob**

```json
{ "id": 123 }
```

**`GET` element maydonlari (namuna):** `id`, `kind`, `title`, `body`, `link_url`, `read_at`, `event_at`, `notify_at`, `parent_id`, `subject_user_id`, `subject_user_label`, `created_at`.

---

### 4.2 Полезное (foydali)

| METHOD | URL | Auth | Vazifa |
|--------|-----|------|--------|
| `GET` | `/api/me/notifications/useful/` | JWT | Yangilanishlar + maslahatlar (maslahatlar — obuna/qabul qilishga bog‘liq) |
| `POST` | `/api/me/notifications/useful/seen/` | JWT | Tab ko‘rilgan (`{}` bilan ham bo‘lishi mumkin) |
| `GET` | `/api/me/tip-settings/` | JWT | `tips_per_day`, `useful_subscribed` |
| `PATCH` | `/api/me/tip-settings/` | JWT | Sozlamalarni yangilash |
| `POST` | `/api/me/disease-tip-subscribe/<disease_id>/` | JWT | Kasallik bo‘yicha maslahatga obuna |
| `DELETE` | `/api/me/disease-tip-subscribe/<disease_id>/` | JWT | Obunani o‘chirish |

**`PATCH /api/me/tip-settings/` body**

| Maydon | Turi | Majburiy | Tavsif |
|--------|------|----------|--------|
| `tips_per_day` | `integer` | yo‘q | 1…20 |
| `useful_subscribed` | `boolean` | yo‘q | «Полезное» kanaliga obuna |

**`GET /api/me/notifications/useful/`** javob: birlashtirilgan massiv. Elementlar:
- `"type": "update"` — `id`, `title`, `body`, `at`
- `"type": "tip"` — `id`, `title`, `body`, `disease_id`, `at`

---

### 4.3 Qo‘ng‘iroqcha (badge)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/me/notifications/badge/` |
| **Auth** | JWT |

**Javob**

| Maydon | Turi | Tavsif |
|--------|------|--------|
| `events_unread` | `integer` | O‘qilmagan hodisalar |
| `events_unread_today` | `integer` | Bugun yaratilgan, o‘qilmagan |
| `useful_unread` | `integer` | Foydali bo‘limda „yangi“ hisob |
| `open_tab` | `"events"` \| `"useful"` \| `"none"` | Ikkalasi ham bo‘lsa — `"events"` |

---

### 4.4 WebSocket (real vaqt)

| | |
|--|--|
| **URL** | `ws://{HOST}:{PORT}/ws/notifications/?token=<JWT_access>` |
| **Token** | **xuddi REST uchun ishlatiladigan `access` token** (query string) |

HTTPS muhitida: `wss://.../ws/notifications/?token=...`

---

## 5. Заметка (eslatma)

TZ da alohida «Заметка» REST bo‘lmasa-da, backendda asosiy joy — **dorilar shkafidagi yozuv**:

**Model:** `CabinetItem` maydoni **`note`** («Заметка»).

| METHOD | URL | Auth |
|--------|-----|------|
| `GET` | `/api/me/cabinet/items/` | JWT |
| `POST` | `/api/me/cabinet/items/` | JWT |
| `GET` | `/api/me/cabinet/items/<pk>/` | JWT |
| `PATCH` | `/api/me/cabinet/items/<pk>/` | JWT |
| `DELETE` | `/api/me/cabinet/items/<pk>/` | JWT |

**Yaratish / yangilashda `note`**

| Maydon | Turi | Majburiy | Tavsif |
|--------|------|----------|--------|
| `note` | `string` | yo‘q | Bo‘sh qoldirsa ham bo‘ladi |
| `drug` | `integer` \| `null` | shartli* | Spravochnikdan dori ID yoki |
| `custom_name` | `string` | shartli* | Agar `drug` bo‘lmasa — nom |
| `expires_at` | `string` (YYYY-MM-DD) \| `null` | yo‘q | Yaroqlilik muddati |
| `photo` | `file` | yo‘q | Multipart |

\* Kamida bittasi: `drug` yoki `custom_name` (yangi yozuvda).

---

## 6. Конфиденциальность (Maxfiylik)

Statik sahifa slug orqali (admin bilan kelishiladi; odatda `privacy`).

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/content/pages/<slug>/` |
| **Auth** | kerak emas |

**Path parametrlar**

| Parametr | Turi | Tavsif |
|----------|------|--------|
| `slug` | `string` | Masalan **`privacy`** |

**Javob `200`**

```json
{
  "slug": "privacy",
  "title": "...",
  "body": "<html или текст>"
}
```

**`404`** — sahifa yo‘q yoki `is_active=false`.

---

## 7. О компании

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/content/pages/<slug>/` |
| **Auth** | kerak emas |

Odatiy slug: **`about`** *(admin tasdiqlashi kerak)*.

**Javob:** `slug`, `title`, `body`.

---

## 8. Обратная связь — **Чат** va **Письмо (xat)**

### 8.1 Xat («Отправить письмо») — fikr-mulohaza

| | |
|--|--|
| **METHOD** | `POST` |
| **URL** | `/api/support/feedback/` |
| **Auth** | JWT |

**Body (JSON)**

| Maydon | Turi | Majburiy |
|--------|------|----------|
| `message` | `string` (max 8000) | ha |
| `subject` | `string` (max 255) | yo‘q |
| `email` | `string` (email) | yo‘q *(bo‘lmasa, user.email ishlatiladi)* |

**Javob `201`:** `{ "ok": true }`

---

### 8.2 Qo‘llab-quvvatlash chati

**Tredlar**

| METHOD | URL | Auth |
|--------|-----|------|
| `GET` | `/api/me/chat/threads/` | JWT |
| `POST` | `/api/me/chat/threads/` | JWT |

**`POST` body**

| Maydon | Turi | Majburiy | Default |
|--------|------|----------|---------|
| `title` | `string` (max 255) | yo‘q | `"Поддержка"` |

**Javob `201`:** `id`, `title`.

**Xabarlar**

| METHOD | URL | Auth |
|--------|-----|------|
| `GET` | `/api/me/chat/threads/<thread_id>/messages/` | JWT |
| `POST` | `/api/me/chat/threads/<thread_id>/messages/` | JWT |

**`POST` body**

| Maydon | Turi | Majburiy |
|--------|------|----------|
| `body` | `string` | ha (bo‘sh emas) |

---

## 9. Аптеки va Больницы (dorixonalar va shifoxonalar)

### 9.1 Shaharlar

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/geo/cities/` |
| **Auth** | kerak emas |

**Query**

| Parametr | Turi | Majburiy | Default | Tavsif |
|----------|------|----------|---------|--------|
| `q` | `string` | yo‘q | — | Nom bo‘yicha qidiruv |
| `limit` | `integer` | yo‘q | `200` | Max `500` |

**Javob:** `[{ "id": 1, "name": "..." }, ...]`

---

### 9.2 Muassasalar ro‘yxati (apteka / kasalxona)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/geo/facilities/` |
| **Auth** | kerak emas |

**Query**

| Parametr | Turi | Majburiy | Tavsif |
|----------|------|----------|--------|
| `kind` | `string` | yo‘q | `"pharmacy"` \| `"hospital"` |
| `city_id` | `integer` | yo‘q | Shahar `id` |
| `q` | `string` | yo‘q | Nom yoki manzil bo‘yicha |

**Javob:** masiv — `id`, `kind`, `name`, `address`, `phone`, `hours_text`, `latitude`, `longitude`, `city_id`, `city_name`.

---

### 9.3 Muassasa kartochkasi

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/geo/facilities/<pk>/` |
| **Auth** | kerak emas |

**Javob:** `city` ichida `{ "id", "name" }`; qolgan maydonlar yuqoridagi kabi.

---

## 10. Заболевания (kasalliklar ma’lumotnomasi)

### 10.1 Ro‘yxat

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/catalog/diseases/` |
| **Auth** | kerak emas |

**Query**

| Parametr | Turi | Majburiy |
|----------|------|----------|
| `q` | `string` | yo‘q |

**Javob:** `id`, `name`, `description`, `created_at`, `updated_at`.

---

### 10.2 Kartochka (dorilar bilan)

| | |
|--|--|
| **METHOD** | `GET` |
| **URL** | `/api/catalog/diseases/<pk>/` |
| **Auth** | kerak emas |

**Javob:** asosiy kasallik maydonlari + **`drugs`** — qisqa dori kartochkalari (`id`, `name`, `description`, `dosage`, `image`, `rating`), max ~80 ta.

---

## 11. Qisqa cheat-sheet

```
POST   /api/auth/login/          → tokens.access + tokens.refresh
POST   /api/auth/refresh/       → yangi access
GET    /api/catalog/symptoms/?q=
GET    /api/catalog/body-parts/
GET    /api/faq/?q=
POST   /api/assistant/diagnose/
GET    /api/assistant/diagnoses/

GET    /api/me/notifications/events/
POST   /api/me/notifications/events/
POST   /api/me/notifications/events/<pk>/read/
GET    /api/me/notifications/useful/
POST   /api/me/notifications/useful/seen/
GET    /api/me/notifications/badge/
GET|PATCH /api/me/tip-settings/

GET    /api/content/pages/privacy/
GET    /api/content/pages/about/

POST   /api/support/feedback/
GET|POST /api/me/chat/threads/
GET|POST /api/me/chat/threads/<id>/messages/

GET    /api/geo/cities/
GET    /api/geo/facilities/
GET    /api/geo/facilities/<pk>/

GET    /api/catalog/diseases/
GET    /api/catalog/diseases/<pk>/

PATCH  /api/me/cabinet/items/<pk>/   (maydon: note, ...)
WS     /ws/notifications/?token=<access>
```

---

## 12. Qo‘shimcha

- Batafsil barcha endpointlar: Swagger **`/docs/`**, sxema **`/schema/`**.
- Xatoliklar odatda DRF formatida: `{"detail": "..."}` yoki maydon-xato obyekti.
- Medic tavsiyasi: **`access`** muddati tugaganda **refresh** orqali yangilash; **refresh** tugasa qayta **login**.

*Hujjat loyiha kodiga mos yozilgan; production URL va slug qiymatlarini devops/admin bilan tasdiqlang.*
