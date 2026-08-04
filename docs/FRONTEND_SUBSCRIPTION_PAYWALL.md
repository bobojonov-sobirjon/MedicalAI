# Frontend Integration: Trial, Paywall, Subscription

Bu hujjat frontend jamoa uchun. Maqsad: mijoz talab qilgan flow'ni ilovada to'g'ri ko'rsatish.

## Business Rule

1. Yangi foydalanuvchiga `1 sutka` bepul trial beriladi.
2. Trial aktiv bo'lsa, ilovaning barcha bo'limlari ochiq.
3. Trial tugagach, faqat `История болезни` bo'limi ishlaydi.
4. Trial tugagandan keyin boshqa istalgan bo'lim ochilsa, paywall chiqadi:

`Бесплатный период закончился. Оплатить подписку.`

5. `Оплатить подписку` tugmasi bosilganda subscription/payment oynasiga o'tish kerak.

## Frontend Nima Qilishi Kerak

Frontend 2 xil holatni qo'llab-quvvatlashi kerak:

1. Oldindan subscription status'ni olib, UI'ni bloklash.
2. Agar user baribir yopiq bo'lim endpoint'iga kirsa, backend qaytargan `403` ni ushlab paywall ko'rsatish.

Ya'ni faqat UI bilan yashirish emas, backend javobi ham ushlansin.

## Asosiy Endpointlar

### 1. Subscription status

`GET /api/billing/subscription/`

Bu endpoint user access holatini beradi.

### 2. Tarifflar

`GET /api/billing/tariffs/`

Payment ekranida tariflarni chiqarish uchun.

### 3. Payment yaratish

`POST /api/billing/payments/create/`

Request body:

```json
{
  "tariff_slug": "standard"
}
```

Yoki:

```json
{
  "tariff_slug": "premium"
}
```

Response ichida `payment_url` keladi. Frontend shu URL'ni WebView yoki browser ichida ochadi.

### 4. Payment status tekshirish

`GET /api/billing/payments/{payment_id}/`

Payment muvaffaqiyatli bo'lgach subscription holatini yangilash uchun ishlatiladi.

## Subscription Status Response

`GET /api/billing/subscription/` javobida quyidagi muhim maydonlar bor:

```json
{
  "has_active_subscription": true,
  "is_trial_active": true,
  "is_paid_active": false,
  "requires_payment": false,
  "free_trial_used": true,
  "can_get_free_trial": false,
  "access_scope": "full",
  "allowed_sections": ["all"],
  "trial_days": 1,
  "seconds_left": 86000,
  "hours_left": 24,
  "days_left": 1,
  "tariff": {
    "slug": "free_trial",
    "tier": "free_trial",
    "title": "Пробный период",
    "description": "Бесплатный доступ 24 часа при регистрации. Выдаётся один раз.",
    "price_rub": "0.00",
    "started_at": "2026-08-04T09:00:00Z",
    "expires_at": "2026-08-05T09:00:00Z",
    "seconds_left": 86000,
    "hours_left": 24,
    "days_left": 1,
    "source": "auto_trial",
    "is_trial": true,
    "is_paid": false
  },
  "limits": {},
  "paywall": null
}
```

### Muhim maydonlar

- `is_trial_active` — `true` bo'lsa paywall **chiqarilmasin**, hamma bo'lim ochiq (24 soat)
- `is_paid_active` — pullik Standard/Premium aktiv
- `requires_payment` — `true` bo'lsagina paywall ko'rsatilsin
- `has_active_subscription` — faqat **to'liq ruxsat** (trial yoki paid) uchun `true`
- `access_scope`
  - `full` -> hamma bo'lim ochiq
  - `history_only` -> faqat `История болезни` ochiq
- `days_left` / `hours_left` / `seconds_left` — qolgan muddat (ceil). 24 soatlik trial uchun boshida `days_left=1`, `hours_left=24`
- `paywall` — faqat `requires_payment=true` da keladi

### Frontend qoida (majburiy)

```text
if (is_trial_active || is_paid_active || access_scope == "full") {
  // hamma ochiq, subscription screen majburiy emas
} else if (requires_payment || access_scope == "history_only") {
  // faqat history; boshqa bo'limda paywall
}
```

**Xato:** `days_left === 0` ni darhol "tugadi" deb o'qimang — `seconds_left` / `hours_left` / `is_trial_active` ni tekshiring.

## Trial Tugagandan Keyingi Response

Misol:

```json
{
  "has_active_subscription": false,
  "is_trial_active": false,
  "is_paid_active": false,
  "requires_payment": true,
  "free_trial_used": true,
  "can_get_free_trial": false,
  "access_scope": "history_only",
  "allowed_sections": ["history"],
  "tariff": {
    "slug": "free",
    "tier": "free",
    "title": "Бесплатный",
    "description": "После окончания пробного периода доступен только раздел истории болезни.",
    "price_rub": "0.00",
    "expires_at": null,
    "days_left": null,
    "source": "auto_free",
    "is_trial": false,
    "is_paid": false
  },
  "limits": {},
  "paywall": {
    "title": "Бесплатный период закончился",
    "message": "Бесплатный период закончился. Оплатить подписку.",
    "cta_text": "Оплатить подписку",
    "cta_action": "open_subscription_payment"
  }
}
```

## История болезней — kasallik qidiruvi

Yangi yozuv qo'shishda kasallikni qidirish uchun:

`GET /api/catalog/diseases/?q=Панкреатит`

yoki:

`GET /api/catalog/diseases/?search=Панкреатит`

- `q` / `search` ikkalasi ham ishlaydi
- javob engil: `id`, `name`, `description_preview`
- bu endpoint history_only userga ham ochiq (picker uchun)

## Dori (drugs) performance

- List: `GET /api/catalog/drugs/?q=...&page=1&page_size=50` — faqat nom/doza bo'yicha qidiradi, nested diseases yo'q
- Detail: `GET /api/catalog/drugs/{id}/` — nested limit bilan
- Tez detail: `GET /api/catalog/drugs/{id}/?include_related=false` — faqat tavsif, diseases yo'q

## Qaysi Bo'lim Ochiq, Qaysi Yopiq

### `access_scope = full`

Hamma bo'limlar ochiq:

- Catalog
- Drugs
- Diseases
- Assistant
- Cabinet
- Notifications
- Geo / facilities
- Reviews / discussions
- Relax
- Support
- Boshqa feature bo'limlari
- History

### `access_scope = history_only`

Faqat history bilan bog'liq bo'limlar ochiq:

- `История болезни`
- doctor visits
- analyses
- prescriptions

Qolgan barcha feature bo'limlar yopiq.

## UI Behavior

### Variant A: oldindan bloklash

App ochilganda yoki home screen ochilganda:

1. `GET /api/billing/subscription/` chaqiriladi
2. `access_scope` o'qiladi
3. Agar `history_only` bo'lsa:
   - history section ishlaydi
   - qolgan sectionlar locked ko'rinishda bo'ladi
   - bosilganda paywall modal chiqadi

### Variant B: backend 403 qaytarganda bloklash

Agar frontend userni yopiq bo'limga kirishga qo'ysa va endpoint chaqirilsa, backend `403` qaytaradi.

Misol response:

```json
{
  "detail": "Бесплатный период закончился. Оплатить подписку.",
  "code": "subscription_required",
  "access_scope": "history_only",
  "allowed_sections": ["history"],
  "paywall": {
    "title": "Бесплатный период закончился",
    "message": "Бесплатный период закончился. Оплатить подписку.",
    "cta_text": "Оплатить подписку",
    "cta_action": "open_subscription_payment"
  }
}
```

Frontend qoidasi:

- agar `status = 403`
- va `code = subscription_required`

unda modal ochilsin.

## Modal Matni

Recommended UI:

- Title: `Бесплатный период закончился`
- Body: `Бесплатный период закончился. Оплатить подписку.`
- Primary button: `Оплатить подписку`
- Secondary button: `Позже` yoki close

## Payment Flow

### Flow

1. User `Оплатить подписку` ni bosadi
2. Frontend subscription screen ochadi
3. `GET /api/billing/tariffs/` bilan tariflarni oladi
4. User tarif tanlaydi
5. `POST /api/billing/payments/create/`
6. Response'dan `payment_url` olinadi
7. `payment_url` WebView/browser ichida ochiladi
8. To'lovdan keyin:
   - `GET /api/billing/payments/{payment_id}/` polling
   - yoki `GET /api/billing/subscription/` ni qayta yangilash
9. Agar obuna aktiv bo'lsa, locked sectionlar ochiladi

## App Config

Public config endpoint:

`GET /api/content/config/`

Endi frontend quyidagi fieldni ishlatishi kerak:

```json
{
  "free_trial_days": 1,
  "psychology_email": "psychology@medic-ai.ru"
}
```

Eslatma: frontend eski `free_trial_months` fieldiga tayanayotgan bo'lsa, uni `free_trial_days` ga o'tkazish kerak.

## Tavsiya Qilingan Frontend Qoidasi

### Agar `access_scope = full`

- hamma section enabled
- modal ko'rsatilmaydi

### Agar `access_scope = history_only`

- history enabled
- qolgan sectionlar disabled yoki locked UI
- bosilganda paywall modal
- backend `403 subscription_required` bo'lsa ham xuddi shu modal chiqsin

## Frontend Uchun Qisqa Logic

```text
onAppStart:
  load /api/billing/subscription/
  if access_scope == full:
    allow all sections
  else if access_scope == history_only:
    allow only history

onLockedSectionTap:
  show paywall modal

onApiError:
  if status == 403 and code == subscription_required:
    show paywall modal

onPaywallPrimaryAction:
  open subscription/payment screen
```

## Muhim Eslatma

Frontend faqat UI blok qo'ymasligi kerak. Backend allaqachon himoya qo'ygan. Shuning uchun:

- UI oldindan bloklasin
- va backend'dan kelgan `403 subscription_required` ni ham ushlasin

Shunda flow to'liq va ishonchli ishlaydi.
