# MedicAI — Frontend API

Bitta qo‘llanma. Base: `http://85.198.101.179:8007`  
Katalog (kasallik/dori list/detail) — **AllowAny**. Qolganiga: `Authorization: Bearer <access>`.

---

## 1. Помощник (рука ≠ горло)

**POST** `/api/assistant/diagnose/`

```json
{
  "symptoms": [id],
  "symptoms_text": "болит локоть, затекает указательный палец",
  "body_parts": [id],
  "temperature_c": null,
  "blood_pressure": ""
}
```

Показывать: `possible_conditions` (list строк), `body_parts_resolved`, `answer`, `disclaimer`.

`ai_mode`: `llm` — ответ нейросети; `catalog` — быстрый ответ из справочника (ИИ недоступен / 403 / таймаут). ИИ специально не отключали.

Не искать локально по слову «боль». Бэкенд сам учитывает часть тела. При «Правая рука» не должно быть «Боль в горле / груди / лице».

---

## 2. Лекарства — карточка как Vidal (спойлеры)

**Список (быстро):**

```
GET /api/catalog/drugs/?page=1&page_size=50
GET /api/catalog/drugs/?q=Креон&page=1&page_size=50
```

Брать **`results`**. Не грузить весь каталог одним запросом.

**Карточка:** `GET /api/catalog/drugs/{id}/`

- `description` — абзац(ы) под названием: действие + показания + как принимать (несколько абзацев). Пустым не бывает.
- `sections[]` — спойлеры. Пустые не рисовать. **Не** дублировать весь `instructions` на экране.
- `text` — обычный текст (абзацы, списки `- пункт`). **Без** сырых `**` — бэкенд их убирает. Markdown-рендер не обязателен.
- МКБ-10/11 в UI **не показывать**.
- `inn` — под названием («МНН»).
- `diseases` / `related_diseases` — связанные болезни.  
  `?include_related=false` болезни **не обнуляет**.

```json
{
  "id": 1673,
  "name": "Люголь",
  "inn": "йод",
  "dosage": "раствор 1%",
  "sections": [
    { "key": "composition", "title": "Форма выпуска, упаковка и состав", "text": "…" },
    { "key": "indications", "title": "Показания препарата", "text": "…" }
  ],
  "diseases": [{ "id": 10, "name": "…" }]
}
```

Пикер истории: `GET /api/catalog/drugs/?picker=1` или `GET /api/me/disease-records/drugs/?q=`

---

## 3. Заболевания — список, карточка, скорость

### 3.1 Список экрана «Заболевания» / Главная

**Нельзя:** `GET /api/catalog/diseases/` без пагинации и ждать 11 000 записей (это было ~10 сек).

**Нужно:**

```http
GET /api/catalog/diseases/?page=1&page_size=50
```

Ответ **объект**, не массив:

```json
{
  "count": 11493,
  "page": 1,
  "page_size": 50,
  "next": 2,
  "previous": null,
  "results": [
    {
      "id": 198,
      "name": "Амебиаз",
      "description": "Амебиаз — это заболевание, при котором…",
      "description_preview": "Амебиаз — это заболевание, при котором…"
    }
  ]
}
```

| Параметр | Значение |
|----------|----------|
| `page` | с 1 |
| `page_size` | 20–50 (max 100) |
| `next` | следующая страница или `null` |
| UI | infinite scroll / «Ещё»: `page=2`, `page=3`… |
| Карточка списка | `name` + `description_preview` (уже короткий текст) |
| МКБ | **не показывать**. Кодов в `description` больше нет |

Поиск (массив до 50 строк):

```http
GET /api/catalog/diseases/?q=абсцесс
GET /api/catalog/diseases/?q=абсцесс&limit=50
```

### 3.2 Пикер «Выберите болезнь» (история)

Только `id` + `name`, весь справочник, без тяжёлых текстов (~1с, кэш):

```http
GET /api/catalog/diseases/?picker=1
```

Ответ — **массив**: `[{ "id": 198, "name": "Амебиаз" }, …]`

Локальный фильтр по имени — ок. Не вызывать обычный list без `picker`, «чтобы всё скачать».

### 3.3 Карточка заболевания

```http
GET /api/catalog/diseases/{id}/
```

Полный текст **о самой болезни** (не код МКБ):

| Поле | UI |
|------|-----|
| `name` | заголовок |
| `description` | краткий абзац под названием. Пустым не бывает: если в базе только код МКБ, бэкенд даёт справочный текст. **Не показывать** «Описание отсутствует», если `description` не пустой. |
| `sections[]` | спойлеры, как у лекарства |
| `instructions` | можно не показывать, если есть `sections` |
| `drugs` / `related_drugs` | блок «Лекарства» |
| `drugs_count` | сколько всего связано |
| `drugs_truncated` | `true` — список обрезан |

`sections` (только непустые):

| `key` | `title` |
|-------|---------|
| `overview` | Общие сведения |
| `causes` | Причины |
| `symptoms` | Симптомы |
| `complications` | Осложнения |
| `self_help` | Что можете сделать Вы |
| `treatment` | Лечение |
| `prevention` | Профилактические меры |
| `diagnosis` | Диагностика |

Каждый спойлер: заголовок закрыт, тап → `text` (Markdown, как у лекарств). Пустые заголовки не рисовать. МКБ-коды не показывать.

Пример:

```json
{
  "id": 198,
  "name": "Амебиаз",
  "description": "Амебиаз — это заболевание, при котором в толстой кишке…",
  "sections": [
    { "key": "overview", "title": "Общие сведения", "text": "…" },
    { "key": "causes", "title": "Причины", "text": "…" },
    { "key": "symptoms", "title": "Симптомы", "text": "…" },
    { "key": "treatment", "title": "Лечение", "text": "…" }
  ],
  "drugs": [{ "id": 12342, "name": "Креон", "description_preview": "…" }],
  "drugs_count": 216,
  "drugs_truncated": false
}
```

**Быстрее открыть карточку** (без 300 лекарств):

```http
GET /api/catalog/diseases/{id}/?include_drugs=false
```

Из карточки лекарства (чтобы «Креон» не пропал в длинном списке):

```http
GET /api/catalog/diseases/{id}/?highlight_drug_id=12342
```

Фильтр препаратов на карточке болезни: `?q=Креон`

### 3.4 Что сломает скорость / UI

| Не делать | Делать |
|-----------|--------|
| `GET /diseases/` и ждать весь каталог как массив с текстами | `?page=1&page_size=50` → `results` |
| Показывать «МКБ-10: A42.1» | только название + описание болезни |
| Список лекарств с `diseases/{id}` для пикера истории | `/me/disease-records/drugs/?q=` |

---

## 4. История болезней — форма записи

**Семейные профили (карусель):**

- Список: `GET /api/me/profiles/`
- **Войти как этот человек (главная, история ребёнка/мамы):**  
  `POST /api/me/profiles/{id}/activate/`  
  Ответ: `{ "open": "home", "active_profile_id": …, "profile": {…} }`  
  После этого открывать **главную**, не экран редактирования.
- Редактировать (карандаш): `GET` + `PATCH /api/me/profiles/{id}/`
- `GET /api/auth/me/` → `active_profile_id`
- История/помощник: можно слать `subject_user_id`; если не слать — берётся активный профиль.

**POST не ищет.** Сначала GET, потом POST с id.

| UI | GET | POST |
|----|-----|------|
| Профиль | `/api/me/profiles/` | `subject_user_id` |
| Дата начала | — | `date_of_illness` |
| Название болезни | `/api/catalog/diseases/?q=` или `?picker=1` | `disease_id` |
| Симптомы | — | `symptoms` |
| **Препараты** | **`GET /api/me/disease-records/drugs/?q=Креон`** | **`drug_ids`** |
| Визит врача | после создания | `POST /api/me/disease-records/doctor-visits/` |

```json
POST /api/me/disease-records/
{
  "subject_user_id": 1,
  "date_of_illness": "2022-03-01",
  "disease_id": 55,
  "symptoms": "…",
  "drug_ids": [123, 124]
}
```

```http
GET /api/me/disease-records/drugs/?q=Креон
```

Без `q` — полный лёгкий список. Либо `GET /api/catalog/drugs/?picker=1`.

---

## 5. Обратная связь

Кнопка **Отправить**. Поля: **Почта обратной связи** + **Письмо**.

`POST /api/support/feedback/`

```json
{ "email": "user@example.com", "message": "…", "subject": "Обратная связь" }
```

`email` и `message` обязательны. SMTP на FE не нужен.

---

## 6. Аптечка

Искать: `GET /api/catalog/drugs/?q=Нурофен&page=1&page_size=20`  
Добавить: `POST /api/me/cabinet/items/` `{ "drug_id": 123, "expires_at": "2027-01-01" }`

Название / инструкция / болезни — из `drug_detail`.  
Фото: `POST /api/me/cabinet/recognize/` — если `catalog_match=false`, выбрать из поиска.

---

## 7. Trial / paywall

24ч trial → всё открыто. После — только **История болезни**.

`GET /api/billing/subscription/`

- `is_trial_active` / `is_paid_active` / `access_scope` (`full` \| `history_only`)
- `requires_payment` → paywall
- не закрывать trial по `days_left === 0` — смотреть `seconds_left` / `is_trial_active`

`403` + `code: subscription_required` → тот же paywall.  
Оплата: `GET /api/billing/tariffs/` → `POST /api/billing/payments/create/` → `payment_url`.  
Config: `GET /api/content/config/` → `free_trial_days`.

При `history_only` пикеры открыты: `/catalog/diseases/?picker=1`, `/catalog/drugs/?picker=1`, `/me/disease-records/drugs/`.

---

## Канон endpoint’ов

| Что | Endpoint |
|-----|----------|
| Список болезней (главная) | `GET /api/catalog/diseases/?page=1&page_size=50` → `results` |
| Поиск болезни | `GET /api/catalog/diseases/?q=` |
| Пикер болезни | `GET /api/catalog/diseases/?picker=1` |
| Карточка болезни | `GET /api/catalog/diseases/{id}/` |
| Список лекарств | `GET /api/catalog/drugs/?page=1&page_size=50` → `results` |
| Пикер лекарства | `GET /api/me/disease-records/drugs/?q=` |
| Город | `GET /api/geo/cities/` |
