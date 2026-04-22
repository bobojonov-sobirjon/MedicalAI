# MedicalAI Backend (Django + DRF)

Backend API for **MedicAI / MedicalAI** mobile app.

## Stack

- **Python / Django**
- **Django REST Framework**
- **JWT** (`rest_framework_simplejwt`)
- **Swagger / OpenAPI** (`drf-spectacular`)
- **Jazzmin** (admin UI)
- **PostgreSQL**

## Quick start

### 1) Create venv & install deps

```bash
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

### 2) Configure `.env`

Create `.env` in project root (next to `manage.py`).

Minimal for local dev:

```env
DB_NAME=medical_ai
DB_USER=postgres
DB_PASSWORD=0576
DB_HOST=localhost
DB_PORT=5432

# Email (for forgot password)
# If you don't want real SMTP in dev, set console backend:
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=no-reply@medicalai.local

# Forgot password TTL (minutes)
PASSWORD_RESET_CODE_TTL_MINUTES=15
PASSWORD_RESET_SESSION_TTL_MINUTES=15

# VK / Firebase (optional, only if you use social login)
VK_ANDROID_CLIENT_ID=...
VK_ANDROID_CLIENT_SECRET=...
VK_IOS_CLIENT_ID=...
VK_IOS_CLIENT_SECRET=...
VK_REDIRECT_URI=...
VK_API_VERSION=5.199
```

If you want real email sending (SMTP), remove `EMAIL_BACKEND` and set:

```env
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=your@gmail.com
```

### 3) Migrate & run

```bash
python manage.py migrate
python manage.py runserver
```

## API Docs (Swagger)

- Swagger UI: `http://localhost:8000/docs/`
- Schema: `http://localhost:8000/schema/`

Tags in Swagger:

- **Auth** — register/login/refresh/social/password
- **User Details** — current user profile (GET/PATCH)
- **Diseases**, **Drugs** — public directories (read-only)
- **My Health** + nested tags — private medical history

## Auth (JWT)

### Register

`POST /api/auth/register/`

Required:
- `email`
- `username`
- `password` (min 6, must contain **letters + digits**)

Optional:
- `phone_number`, `first_name`, `last_name`

### Login

`POST /api/auth/login/`

Send:
- `identifier` — **username OR email OR phone_number**
- `password`

### Refresh

`POST /api/auth/refresh/`

## Forgot password (email код) — ТЗ §7.5

Flow is split into 3 steps:

1) **Request code**

`POST /api/auth/password/forgot/request/`

```json
{ "email": "user@example.com" }
```

2) **Verify code** → returns `reset_token`

`POST /api/auth/password/forgot/verify/`

```json
{ "email": "user@example.com", "code": "123456" }
```

3) **Reset password** → returns JWT + user

`POST /api/auth/password/forgot/reset/`

```json
{ "reset_token": "<token>", "new_password": "newpass1" }
```

Email template:
- `templates/emails/password_reset.html`

## Change password (logged in)

`POST /api/auth/password/change/`

```json
{ "old_password": "oldpass1", "new_password": "newpass1" }
```

## Profile (User Details)

`GET /api/auth/me/` — current user profile  
`PATCH /api/auth/me/` — update profile

Fields include:
- `first_name`, `last_name`, `avatar`
- `nickname`, `gender`, `city`, `date_of_birth`, `height_cm`, `weight_kg`

## Catalog

Public read-only endpoints:

- Diseases:
  - `GET /api/catalog/diseases/` (optional `?q=...`)
  - `GET /api/catalog/diseases/{id}/`
- Drugs:
  - `GET /api/catalog/drugs/` (optional `?q=...`)
  - `GET /api/catalog/drugs/{id}/`

Drug fields include:
- `rating` (default `0`)
- `diseases` — **Можно лечить** (ManyToMany to diseases)

## My Health (private)

All endpoints require JWT (current user only).

Main records:
- `GET/POST /api/me/disease-records/`
- `GET/PATCH/DELETE /api/me/disease-records/{id}/`

Nested create endpoints:
- `POST /api/me/disease-records/{record_id}/doctor-visits/`
- `POST /api/me/disease-records/{record_id}/analyses/`
- `POST /api/me/disease-records/{record_id}/prescriptions/`

Note: nested payloads **do not accept manual `id`**.

## Fake data

Create fake diseases + drugs:

```bash
python manage.py add_fake_datas
```

Options:
- `--count 100`
- `--seed 42`

It also randomly fills `Drug.diseases` (“Можно лечить”).

## Admin

Admin panel:
- `http://localhost:8000/admin/`

Customizations:
- `Groups` and `Sites` are hidden from admin menu
- `SocialAccount` and `PasswordResetCode` are shown **inline** on the User page

