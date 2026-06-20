# MedicAI — Оплата, тарифы и Free Trial (Mobile API)

Документация для **мобильных разработчиков** (Flutter / React Native / native).

---

## 1. Общая информация

| Параметр | Значение |
|----------|----------|
| **Проект** | MedicAI Backend |
| **Framework** | Django + Django REST Framework |
| **Аутентификация** | JWT (`rest_framework_simplejwt`) |
| **Content-Type** | `application/json` |
| **Swagger** | `/docs/` |

### Base URL

| Окружение | URL |
|-----------|-----|
| **Local dev** | `http://127.0.0.1:8000` |
| **Staging / Server** | `http://85.198.101.179:8007` |
| **Production (план)** | `https://api.medic-ai.ru` |

Все endpoint'ы ниже с префиксом **`/api/`**.

### Заголовки (защищённые запросы)

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

Опционально (если включено на сервере):

```http
X-Backend-Key: <BACKEND_API_KEY>
```

---

## 2. Аутентификация (JWT)

### 2.1 Регистрация (+ автоматический Free Trial)

| | |
|---|---|
| **METHOD** | `POST` |
| **URL** | `/api/auth/register/` |
| **Auth** | Не требуется |

**Body:**

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `email` | string | **да** | Уникальный email |
| `username` | string | **да** | Уникальный логин |
| `password` | string | **да** | Мин. 6 символов, минимум 1 буква и 1 цифра |
| `phone_number` | string | нет | Уникальный телефон |
| `first_name` | string | нет | Имя |
| `last_name` | string | нет | Фамилия |

**Пример запроса:**

```json
{
  "email": "user@example.com",
  "username": "user123",
  "password": "secret123",
  "first_name": "Иван",
  "last_name": "Иванов",
  "phone_number": "+79001234567"
}
```

**Ответ `201`:**

```json
{
  "user": {
    "id": 1,
    "username": "user123",
    "email": "user@example.com",
    "phone_number": "+79001234567",
    "first_name": "Иван",
    "last_name": "Иванов",
    "nickname": "",
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
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
}
```

**Важно:** после регистрации backend **автоматически** выдаёт тариф `free_trial` (см. раздел 3).

---

### 2.2 Вход

| | |
|---|---|
| **METHOD** | `POST` |
| **URL** | `/api/auth/login/` |
| **Auth** | Не требуется |

**Body:**

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `identifier` | string | **да** | `username`, `email` или `phone_number` |
| `password` | string | **да** | Пароль |

**Пример:**

```json
{
  "identifier": "user@example.com",
  "password": "secret123"
}
```

**Ответ `200`:**

```json
{
  "user": { "...": "..." },
  "tokens": {
    "access": "eyJ...",
    "refresh": "eyJ..."
  }
}
```

---

### 2.3 Обновление access-токена

| | |
|---|---|
| **METHOD** | `POST` |
| **URL** | `/api/auth/refresh/` |
| **Auth** | Не требуется |

**Body:**

| Поле | Тип | Обязательно |
|------|-----|-------------|
| `refresh` | string | **да** |

**Ответ `200`:**

```json
{
  "access": "eyJ..."
}
```

---

### 2.4 Социальный вход (Google / Apple / VK)

| | |
|---|---|
| **METHOD** | `POST` |
| **URL** | `/api/auth/social/` |
| **Auth** | Не требуется |

**Body (Google/Apple):**

| Поле | Тип | Обязательно |
|------|-----|-------------|
| `provider` | string | **да** — `google` \| `apple` \| `vk` |
| `id_token` | string | да* | Firebase ID token |

**Body (VK):**

| Поле | Тип | Обязательно |
|------|-----|-------------|
| `provider` | string | **да** — `vk` |
| `code` | string | да* | OAuth code |
| `access_token` | string | да* | Альтернатива code |
| `platform` | string | нет | `android` \| `ios` |

\* Нужен `id_token` **или** `code` / `access_token` для VK.

**Free Trial:** выдаётся только при **создании нового** пользователя (не при повторном входе).

---

## 3. Тарифы и Free Trial — бизнес-логика

### 3.1 Схема жизненного цикла пользователя

```
Регистрация (первый раз)
        ↓
free_trial — 90 дней (3 месяца), полный доступ
        ↓  (за 7 / 3 / 1 день — push + уведомление в приложении)
Trial истёк, не оплатил
        ↓
free — бессрочно, ограниченный доступ
        ↓
Оплата Standard (399 ₽) или Premium (999 ₽)
        ↓
paid тариф — 30 дней
        ↓
Срок истёк → снова free
```

### 3.2 Все тарифы в системе

| slug | Название | Цена | Срок | Покупка | Когда назначается |
|------|----------|------|------|---------|-------------------|
| `free_trial` | Пробный период | 0 ₽ | 90 дней | ❌ | Авто при **первой** регистрации |
| `free` | Бесплатный | 0 ₽ | ∞ | ❌ | Авто после окончания trial |
| `standard` | Стандарт | 399 ₽ | 30 дней | ✅ | После оплаты Robokassa |
| `premium` | Премиум | 999 ₽ | 30 дней | ✅ | После оплаты Robokassa |

**Free Trial — только один раз на аккаунт.** Повторно получить нельзя (`free_trial_used: true`).

### 3.3 Лимиты (`limits` в API)

| Ключ | free_trial | free | standard | premium |
|------|------------|------|----------|---------|
| `max_disease_records` | `null` (∞) | `5` | `null` | `null` |
| `max_cabinet_items` | `null` | `3` | `null` | `null` |
| `extended_ai` | `true` | `false` | `true` | `true` |
| `calendar_ai` | `true` | `false` | `true` | `true` |
| `useful_tips` | `true` | `true` | `true` | `true` |
| `family_profiles_max` | — | — | — | `5` |
| `pdf_exports_per_month` | — | — | — | `null` (∞) |
| `doctor_check_discount_percent` | — | — | `50` | — |
| `doctor_checks_discounted_per_month` | — | — | `5` | — |
| `doctor_free_checks_per_month` | — | — | — | `3` |

`null` в числовых лимитах = **без ограничения**.

> На момент v1 лимиты возвращаются в API; жёсткая блокировка на всех endpoint'ах может подключаться поэтапно. Мобильное приложение должно учитывать `limits` для UI.

### 3.4 Уведомления о конце trial

За **7, 3 и 1 день** до окончания `free_trial` пользователь получает:

- запись в разделе **Уведомления** (`kind: system`, `meta.billing: trial_expiring`);
- WebSocket `/ws/notifications/?token=<JWT>`.

Текст: *«Заканчивается бесплатный период — выберите Standard или Premium»*.

### 3.5 Публичная конфигурация

| | |
|---|---|
| **METHOD** | `GET` |
| **URL** | `/api/content/config/` |
| **Auth** | Не требуется |

**Ответ `200`:**

```json
{
  "free_trial_months": 3,
  "psychology_email": "psychology@medic-ai.ru"
}
```

`free_trial_months` × 30 = дней trial (по умолчанию **90**).

---

## 4. API оплаты и подписок

### 4.1 Список тарифов

| | |
|---|---|
| **METHOD** | `GET` |
| **URL** | `/api/billing/tariffs/` |
| **Auth** | Не требуется |

**Ответ `200`:**

```json
[
  {
    "slug": "free_trial",
    "tier": "free_trial",
    "title": "Пробный период",
    "description": "Бесплатный доступ при регистрации. Выдаётся один раз.",
    "price_rub": "0.00",
    "validity_days": 90,
    "limits": {
      "max_disease_records": null,
      "max_cabinet_items": null,
      "extended_ai": true,
      "calendar_ai": true,
      "useful_tips": true
    }
  },
  {
    "slug": "standard",
    "tier": "standard",
    "title": "Стандарт",
    "description": "399 ₽/мес — расширенный AI, аптечка без лимита...",
    "price_rub": "399.00",
    "validity_days": 30,
    "limits": { "...": "..." }
  }
]
```

**Для оплаты** в `payments/create` используйте только `standard` или `premium`.

---

### 4.2 Моя подписка (текущий тариф)

| | |
|---|---|
| **METHOD** | `GET` |
| **URL** | `/api/billing/subscription/` |
| **Auth** | **JWT обязателен** |

**Ответ `200` (есть активная подписка):**

```json
{
  "has_active_subscription": true,
  "free_trial_used": true,
  "can_get_free_trial": false,
  "tariff": {
    "slug": "free_trial",
    "tier": "free_trial",
    "title": "Пробный период",
    "description": "...",
    "price_rub": "0.00",
    "expires_at": "2026-09-14T10:00:00+03:00",
    "days_left": 85,
    "source": "auto_trial"
  },
  "limits": {
    "extended_ai": true,
    "max_disease_records": null
  }
}
```

**Поле `source`:**

| Значение | Описание |
|----------|----------|
| `auto_trial` | Выдан при регистрации |
| `auto_free` | После истечения trial без оплаты |
| `payment` | Оплачен через Robokassa |
| `admin` | Назначен вручную в админке |

**Ответ без подписки:**

```json
{
  "has_active_subscription": false,
  "free_trial_used": true,
  "can_get_free_trial": false,
  "tariff": null,
  "limits": { "...": "..." }
}
```

**Когда вызывать:** при старте приложения, после логина, после возврата с оплаты.

---

### 4.3 Создать платёж (получить ссылку Robokassa)

| | |
|---|---|
| **METHOD** | `POST` |
| **URL** | `/api/billing/payments/create/` |
| **Auth** | **JWT обязателен** |

**Body:**

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `tariff_slug` | string | **да** | `standard` или `premium` |

**Пример:**

```json
{
  "tariff_slug": "standard"
}
```

**Ответ `201`:**

```json
{
  "payment_id": 6,
  "status": "pending",
  "payment_url": "https://auth.robokassa.ru/Merchant/Index.aspx?MerchantLogin=MedicAi&OutSum=399.00&InvId=6&Description=MedicAi+-+Стандарт&SignatureValue=...&IsTest=1",
  "amount_rub": "399.00",
  "tariff_slug": "standard",
  "tariff_title": "Стандарт"
}
```

**Действие мобильного приложения:**

1. Открыть `payment_url` в **WebView** / **Chrome Custom Tabs** / **Safari**.
2. Пользователь платит на **официальной странице Robokassa** (не ваша форма).
3. После возврата — polling статуса (см. 4.4).

**Ошибки:**

| Код | Причина |
|-----|---------|
| `400` | Неверный slug, тариф не покупаемый, Robokassa не настроена |
| `404` | Тариф не найден |
| `401` | Нет JWT |

---

### 4.4 Статус платежа (polling)

| | |
|---|---|
| **METHOD** | `GET` |
| **URL** | `/api/billing/payments/{payment_id}/` |
| **Auth** | **JWT обязателен** |

**Path:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `payment_id` | integer | ID из `payments/create` |

**Ответ `200` (ожидание):**

```json
{
  "payment_id": 6,
  "status": "pending",
  "is_paid": false,
  "amount_rub": "399.00",
  "tariff_slug": "standard",
  "tariff_title": "Стандарт",
  "paid_at": null,
  "created_at": "2026-06-16T10:00:00+03:00",
  "subscription": null
}
```

**Ответ `200` (успех):**

```json
{
  "payment_id": 6,
  "status": "paid",
  "is_paid": true,
  "amount_rub": "399.00",
  "tariff_slug": "standard",
  "tariff_title": "Стандарт",
  "paid_at": "2026-06-16T10:05:00+03:00",
  "created_at": "2026-06-16T10:00:00+03:00",
  "subscription": {
    "has_active_subscription": true,
    "tariff": {
      "slug": "standard",
      "days_left": 30,
      "source": "payment"
    },
    "limits": { "...": "..." }
  }
}
```

**Статусы `status`:**

| Значение | Описание |
|----------|----------|
| `pending` | Ожидает оплаты |
| `paid` | Оплачен, подписка активирована |
| `failed` | Ошибка (сумма, подпись и т.д.) |
| `cancelled` | Отменён |

**Polling:** каждые **2–3 сек**, максимум **60 сек** после возврата из WebView.

---

### 4.5 История платежей

| | |
|---|---|
| **METHOD** | `GET` |
| **URL** | `/api/billing/payments/` |
| **Auth** | **JWT обязателен** |

**Ответ `200`:** массив до 50 последних платежей.

```json
[
  {
    "id": 6,
    "tariff_slug": "standard",
    "tariff_title": "Стандарт",
    "amount_rub": "399.00",
    "status": "paid",
    "paid_at": "2026-06-16T10:05:00+03:00",
    "created_at": "2026-06-16T10:00:00+03:00"
  }
]
```

---

### 4.6 Robokassa callback URL (для справки)

Эти endpoint'ы вызывает **Robokassa** или **браузер**, не мобильное приложение напрямую.

| URL | Кто вызывает | Auth |
|-----|--------------|------|
| `GET/POST /api/billing/robokassa/result/` | Сервер Robokassa | Нет |
| `GET /api/billing/robokassa/success/` | Браузер после успеха | Нет |
| `GET /api/billing/robokassa/fail/` | Браузер при отмене | Нет |

**Success URL** при наличии `OutSum`, `InvId`, `SignatureValue` в query **подтверждает платёж** на backend (fallback, если Result URL недоступен).

**Ответ success:**

```json
{
  "ok": true,
  "message": "Оплата подтверждена. Вернитесь в приложение.",
  "payment_id": 6,
  "status": "paid"
}
```

---

## 5. Полный flow оплаты (Mobile)

```
┌─────────────────┐
│ Экран тарифов   │
│ GET /tariffs/   │
└────────┬────────┘
         │ Пользователь выбрал Standard/Premium
         ▼
┌─────────────────────────────┐
│ POST /payments/create/      │
│ { "tariff_slug": "standard" }│
└────────┬────────────────────┘
         │ payment_url
         ▼
┌─────────────────────────────┐
│ WebView → auth.robokassa.ru │
│ (демо: кнопка Successfully) │
└────────┬────────────────────┘
         │ redirect на success URL
         ▼
┌─────────────────────────────┐
│ Закрыть WebView             │
│ GET /payments/{id}/ polling │
│ пока is_paid == true        │
└────────┬────────────────────┘
         ▼
┌─────────────────────────────┐
│ GET /subscription/          │
│ Показать активный тариф       │
└─────────────────────────────┘
```

### Псевдокод (Dart / Kotlin-подобный)

```text
final res = await api.post('/api/billing/payments/create/', {
  'tariff_slug': 'standard',
});
final paymentId = res['payment_id'];
await launchWebView(res['payment_url']);

for (int i = 0; i < 30; i++) {
  await Future.delayed(Duration(seconds: 2));
  final st = await api.get('/api/billing/payments/$paymentId/');
  if (st['is_paid'] == true) {
    showSuccess();
    break;
  }
}
```

---

## 6. Тестовый режим Robokassa

На сервере: `ROBOKASSA_TEST_MODE=true` → в `payment_url` есть `IsTest=1`.

### 6.1 Демо-режим (основной способ теста)

После открытия `payment_url` появляется жёлтый баннер **«Вы находитесь в демо режиме»**.

Далее экран **«How to complete a test operation?»**:

| Кнопка | Результат |
|--------|-----------|
| **Successfully** | Успешная оплата (симуляция) |
| **Error** | Отказ / ошибка |

**Реальные деньги не списываются.**

### 6.2 Тестовые карты

В демо-режиме Robokassa часто **не требует** карту — достаточно **Successfully**.

Если открывается форма карты, можно попробовать (не гарантировано для всех магазинов):

| Поле | Значение |
|------|----------|
| Номер | `4111 1111 1111 1111` |
| Срок | `12/30` |
| CVC | `123` |

Точные тестовые карты смотрите в **личном кабинете Robokassa → Тестовый режим / документация**.

### 6.3 Важно для теста

1. Используйте **тестовые пароли** из блока «Параметры проведения тестовых платежей» (не боевые).
2. В кабинете: алгоритм хеша **MD5** для теста.
3. Проверяйте API на **том же сервере**, где создавали платёж (`85.198.101.179:8007`, не `127.0.0.1`).
4. Каждый тест — **новый** `POST /payments/create/` (новый `payment_id`).
5. На HTTP браузер может показать «Not secure» → нажмите **Send anyway**.

---

## 7. UI-рекомендации для мобильного приложения

### Экран «Подписка»

Показывать из `GET /api/billing/subscription/`:

- Текущий тариф (`tariff.title`)
- Осталось дней (`tariff.days_left`) — если не `null`
- Бейдж: «Пробный период» / «Стандарт» / «Премиум» / «Бесплатный»
- Кнопки «Подключить Standard» / «Premium» — если `tier` in (`free`, `free_trial`) или срок скоро истекает

### Блокировка функций

Используйте `limits`:

```dart
if (subscription.limits['extended_ai'] != true) {
  showPaywall();
}
if (subscription.limits['max_disease_records'] != null) {
  final max = subscription.limits['max_disease_records'];
  // сравнить с текущим количеством записей
}
```

### После регистрации

Сразу вызвать `GET /api/billing/subscription/` — должен быть `free_trial` с `source: auto_trial`.

---

## 8. Коды ошибок HTTP

| Код | Значение |
|-----|----------|
| `200` | OK |
| `201` | Создано (регистрация, платёж) |
| `400` | Невалидные данные |
| `401` | Нет или истёк JWT |
| `404` | Платёж / тариф не найден |

---

## 9. Чеклист интеграции

- [ ] JWT: login/register → сохранить `access` + `refresh`
- [ ] После регистрации: `GET /subscription/` → `free_trial`
- [ ] Экран тарифов: `GET /tariffs/` → показать `standard`, `premium`
- [ ] Оплата: `POST /payments/create/` → WebView `payment_url`
- [ ] Polling: `GET /payments/{id}/` до `is_paid`
- [ ] Финал: `GET /subscription/` → `source: payment`
- [ ] Уведомления: слушать WS / раздел событий для `trial_expiring`

---

## 10. Связанные endpoint'ы

| URL | Описание |
|-----|----------|
| `GET /api/auth/me/` | Профиль пользователя |
| `GET /api/content/config/` | `free_trial_months` |
| `WS /ws/notifications/?token=` | Real-time уведомления |

---

*Версия документа: 2026-06-16 · Backend: apps/billing*
