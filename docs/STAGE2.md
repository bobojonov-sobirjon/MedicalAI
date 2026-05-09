# Stage 2 — AI (Gemini), OCR, аптечка, недавние просмотры

Полный перечень API по ТЗ (включая уведомления, учреждения, отзывы, чат и т.д.): см. **[TZ_API.md](./TZ_API.md)**.

## Обзор

В проект добавлены: интеграция **Google Gemini**, эндпоинт **помощника по симптомам**, **OCR** для фото анализов, модуль **«Моя аптечка»**, **распознавание лекарства по фото**, учёт **недавно просмотренных лекарств** и флаг **`in_my_cabinet`** в ответе справочника по лекарствам.

## Переменные окружения

| Переменная        | Назначение                                      |
|-------------------|-------------------------------------------------|
| `GEMINI_API_KEY`  | Ключ Google AI Studio / Gemini API              |
| `GEMINI_MODEL`    | Необязательно; по умолчанию `gemini-2.0-flash`  |

Ключ не коммитить в git; хранить только в `.env` на сервере.

## Новые и изменённые файлы

- `apps/core/gemini.py` — вызовы Gemini (JSON-текст, OCR анализа, распознавание упаковки).
- `apps/assistant/` — сервис подбора по справочнику + Gemini, `POST /api/assistant/diagnose/`.
- `apps/cabinet/` — модель `CabinetItem`, CRUD, распознавание, недавние просмотры.
- `apps/catalog/models.py` — модель `DrugViewLog`.
- `apps/catalog/serializers.py` — поле `in_my_cabinet` в `DrugSerializer` (если пользователь авторизован).
- `apps/history/views.py` — `AnalysisOcrView`, маршрут `POST /api/me/analyses/<id>/ocr/`.
- `config/settings.py` — `GEMINI_*`, приложения `cabinet`, `assistant`, теги Swagger, Jazzmin.
- `config/urls.py` — подключение `assistant` и `cabinet`.
- `requirements.txt` — `google-generativeai`.

## API (все под префиксом `/api/`)

### Помощник

- **`POST assistant/diagnose/`** (JWT)  
  Тело JSON: `symptoms` (обязательно), опционально `body_parts` (массив строк), `temperature_c`, `blood_pressure`.  
  Ответ: `catalog_candidates`, `catalog_matched`, `ai` (summary, possible_conditions, suggested_next_steps, disclaimer).  
  Если ключа Gemini нет или ошибка API — возвращается fallback только по локальному справочнику.

### OCR анализа

- **`POST me/analyses/<id>/ocr/?mode=append|replace`** (JWT)  
  У записи анализа должно быть поле `photo`. Текст дописывается в `result_text` (append) или заменяется (replace).

### Аптечка

- **`GET|POST me/cabinet/items/`** — список / создание (`drug` id и/или `custom_name`, `expires_at`, `note`, `photo`).
- **`GET|PATCH|DELETE me/cabinet/items/<id>/`**
- **`POST me/cabinet/recognize/`** — `multipart/form-data`, поле **`image`**. Ответ: `recognized_name`, `matched_drug_id`, `matched_drug`.

### Недавние лекарства (ТЗ)

- **`POST catalog/drugs/<id>/view/`** (JWT) — зафиксировать просмотр карточки.
- **`GET me/recent-drugs/?limit=30`** — список недавно открытых (поле `title` для UI).

### Справочник лекарств

- В **`DrugSerializer`** для авторизованного пользователя добавлено поле **`in_my_cabinet`** (есть ли препарат в аптечке).

## Миграции

- `catalog.0005_drugviewlog`
- `cabinet.0001_initial`

После `git pull`: `pip install -r requirements.txt` и `python manage.py migrate`.

## Медицинский дисклеймер

Ответы помощника и OCR **не являются медицинским диагнозом**. В промптах и ответах заложено напоминание об очном визите к врачу; продукт ориентирован на информационную поддержку.

## Swagger

Документация: `/docs/` — теги **Assistant**, **Medicine cabinet**, обновлённые **Drugs** / **My Health Analyses**.
