# Profillar va Relaks — API qo‘llanmasi

Baza URL: `/api/`  
Swagger: `/docs/` (taglar: **Профили**, **Релакс**)

---

## 1. Profillar (ТЗ §7.7)

Bitta login ostida bir nechta **tibbiy profil** (o‘zingiz + «Добавить пользователя»).  
Qo‘shilgan profillarga **alohida JWT berilmaydi** — faqat akkaunt egasining tokeni ishlatiladi.

### 1.1. O‘z profilingiz (asosiy LK)

| Metod | URL | Auth |
|--------|-----|------|
| GET | `/api/auth/me/` | JWT |
| PATCH | `/api/auth/me/` | JWT |

Parol, email, telefon, avatar, PIN va boshqalar — shu yerda.

---

### 1.2. Ro‘yxat profillar (karusel / «Учетная запись»)

| Metod | URL | Auth |
|--------|-----|------|
| **GET** | `/api/me/profiles/` | JWT |

**Javob `200`:**

```json
{
  "profiles": [
    {
      "id": 1,
      "is_owner": true,
      "label": "",
      "link_id": null,
      "username": "ivan",
      "first_name": "Иван",
      "last_name": "Иванов",
      "nickname": "",
      "gender": "male",
      "city": "Москва",
      "date_of_birth": "1990-01-15",
      "height_cm": 180,
      "weight_kg": "75.00",
      "chronic_diseases": "",
      "had_covid": true,
      "avatar_url": "https://example.com/media/avatars/..."
    },
    {
      "id": 42,
      "is_owner": false,
      "label": "Мама",
      "link_id": 5,
      "first_name": "Анна",
      "last_name": "Иванова",
      "gender": "female",
      ...
    }
  ],
  "count": 2
}
```

| Maydon | Tavsif |
|--------|--------|
| `is_owner` | `true` — siz (akkaunt egasi) |
| `label` | Karusel yorlig‘i («Мама», «Сын») |
| `id` | Keyingi API larda **`subject_user_id`** / `profile_id` |
| `gender` | Yordamchida figura tanlash uchun (frontend) |

**UI:** pastki sheet / radio — `first_name` + `last_name` yoki `label`.

---

### 1.3. Yangi profil qo‘shish («Добавить пользователя»)

| Metod | URL | Auth |
|--------|-----|------|
| **POST** | `/api/me/profiles/` | JWT |

**Body (JSON):**

| Maydon | Majburiy | Tavsif |
|--------|----------|--------|
| `label` | ha | Karusel yorlig‘i («Мама») |
| `first_name` | ha | Ism |
| `last_name` | yo‘q | Familiya |
| `nickname` | yo‘q | Nik |
| `gender` | yo‘q | `male` \| `female` \| `other` |
| `city` | yo‘q | Shahar |
| `date_of_birth` | yo‘q | `YYYY-MM-DD` |
| `height_cm` | yo‘q | Bo‘y |
| `weight_kg` | yo‘q | Vazn |
| `chronic_diseases` | yo‘q | Matn |
| `had_covid` | yo‘q | `true` \| `false` \| `null` |

**Misol:**

```json
{
  "label": "Мама",
  "first_name": "Анна",
  "last_name": "Иванова",
  "gender": "female",
  "date_of_birth": "1960-05-20"
}
```

**Javob `201`:** yaratilgan profil kartochkasi (`ProfileCardSerializer`).

**Eslatma:** yangi user uchun parol **o‘rnatilmaydi** (`unusable password`) — alohida login yo‘q.

---

### 1.4. Bitta profil (qo‘shimcha)

| Metod | URL | Auth |
|--------|-----|------|
| GET | `/api/me/profiles/{profile_id}/` | JWT |
| PUT | `/api/me/profiles/{profile_id}/` | JWT |
| PATCH | `/api/me/profiles/{profile_id}/` | JWT |
| DELETE | `/api/me/profiles/{profile_id}/` | JWT |

`profile_id` — qo‘shimcha profilning **user id** si (`is_owner: false`).  
O‘z profilingiz uchun `GET/PATCH /api/auth/me/` ishlating.

**PATCH/PUT body** (ixtiyoriy maydonlar): `label`, `first_name`, `last_name`, `nickname`, `gender`, `city`, `date_of_birth`, `height_cm`, `weight_kg`, `chronic_diseases`, `had_covid`.

**DELETE `204`:** bog‘lanish o‘chiriladi (profil ro‘yxatdan chiqadi).

---

### 1.5. Tanlangan profil bilan boshqa bo‘limlar

Token **bitta**. Boshqa API larda «kim uchun»:

| Bo‘lim | Parametr |
|--------|----------|
| Yordamchi | `POST /api/assistant/diagnose/` → `subject_user_id` |
| Yordamchi tarixi | `GET /api/assistant/diagnoses/?subject_user_id=` |
| Tarix kasallik | `GET /api/me/disease-records/?subject_user_id=` |
| Eslatmalar | `POST /api/me/notifications/events/` → `subject_user_id` |

`subject_user_id` yo‘q yoki `null` → o‘zingiz uchun (akkaunt egasi).

---

### 1.6. Oqim (mobil)

```
Kirish (JWT)
    → GET /api/me/profiles/
    → Foydalanuvchi profil tanlaydi (activeProfileId)
    → Yordamchi / tarix / … da subject_user_id = activeProfileId
```

---

## 2. Relaks (ТЗ §7.21 / §5.9)

Psixo-emotsional bo‘lim: **GIF**, **video**, **musiqa**. Kontent admin paneldan (`RelaxAsset`).

### 2.1. Lenta

| Metod | URL | Auth |
|--------|-----|------|
| **GET** | `/api/relax/feed/` | **Kerak emas** |

#### Variant A — barcha kategoriyalar

```http
GET /api/relax/feed/
GET /api/relax/feed/?limit=50
```

**Javob `200` (obyekt):**

```json
{
  "gif": [
    {
      "id": 1,
      "title": "Дыхание",
      "category": "gif",
      "url": "https://your-domain.com/media/relax/file.gif",
      "sort_order": 0
    }
  ],
  "video": [ ... ],
  "music": [ ... ]
}
```

#### Variant B — bitta kategoriya

```http
GET /api/relax/feed/?category=gif
GET /api/relax/feed/?category=video
GET /api/relax/feed/?category=music
```

**Javob `200` (massiv):**

```json
[
  {
    "id": 1,
    "title": "Дыхание",
    "category": "gif",
    "url": "https://...",
    "sort_order": 0
  }
]
```

#### Query parametrlar

| Parametr | Tavsif |
|----------|--------|
| `category` | `gif` \| `video` \| `music` (ixtiyoriy) |
| `limit` | Har kategoriya uchun limit (default **200**, max **500**) |

Noto‘g‘ri `category` → **400**.

---

### 2.2. `url` qanday hosil bo‘ladi

Har element uchun:

1. Agar admin **`external_url`** to‘ldirgan bo‘lsa — shu URL.
2. Aks holda yuklangan **`file`** → `PUBLIC_BASE_URL` + media yo‘li.

Frontend to‘g‘ridan-to‘g‘ri `url` ni ochadi (video player, audio, Image/GIF).

---

### 2.3. Admin

Django admin → **«Контент «Релакс»»**:

- Kategoriya: Гиф-анимация / Видео / Музыка  
- Fayl yoki tashqi link  
- `sort_order`, `is_active`

Demo: `python manage.py seed_demo_data`

---

### 2.4. Oqim (mobil)

```
Relaks ekrani
    → GET /api/relax/feed/   (login shart emas)
    → Tab: gif | video | music
    → Element.url bo‘yicha ijro
```

Profil tanlash Relaks uchun **talab qilinmaydi** (umumiy kontent).

---

## 3. Qisqa taqqoslash

| | Profillar | Relaks |
|---|-----------|--------|
| TZ | §7.7 | §7.21, §5.9 |
| Auth | JWT (deyarli hammasi) | Yo‘q |
| Admin | User + FamilyLink | RelaxAsset |
| Asosiy URL | `/api/me/profiles/` | `/api/relax/feed/` |

---

## 4. Xatoliklar (umumiy)

| Kod | Sabab |
|-----|--------|
| 401 | Token yo‘q / eskirgan |
| 403 | Ruxsat yo‘q |
| 404 | Profil topilmadi yoki sizga bog‘lanmagan |
| 400 | Validatsiya (`category`, `subject_user_id`, …) |

---

*Oxirgi yangilanish: profillar — faqat `/api/me/profiles/`; `/api/me/family/` olib tashlangan.*
