# Карточка лекарства: секции как у Vidal (спойлеры)

## Проблема

Сейчас UI показывает только название, МНН/источник (из описания) и **связанные заболевания**.  
У Vidal на карточке есть раскрывающиеся блоки: состав, группы, действие, показания, дозы, побочки…

## API

`GET /api/catalog/drugs/{id}/`

Новое поле **`sections`** — только непустые блоки, в порядке Vidal:

```json
{
  "id": 1,
  "name": "Люголь",
  "inn": "йод",
  "dosage": "раствор 1%",
  "description": "…",
  "instructions": "…полный текст…",
  "sections": [
    {
      "key": "composition",
      "title": "Форма выпуска, упаковка и состав",
      "text": "…"
    },
    {
      "key": "action",
      "title": "Фармакологическое действие",
      "text": "…"
    },
    {
      "key": "indications",
      "title": "Показания препарата",
      "text": "…"
    }
  ],
  "diseases": [ { "id": 10, "name": "…" } ]
}
```

## UI (обязательно)

Для каждого элемента `sections` — **спойлер** (свёрнут по умолчанию):

- заголовок = `title`
- по тапу раскрывается `text`

Связанные заболевания (`diseases`) оставить отдельным блоком, как сейчас.

Пустые секции API **не отдаёт** — не рисуйте заглушки «нет данных» на все Vidal-заголовки.

Типичные `key`: `composition`, `clinical_group`, `pharma_group`, `action`, `pharmacokinetics`, `indications`, `dosing`, `side_effects`, `contraindications`, `special`, `interactions`, `pregnancy`, `contacts`, плюс `inn` / `source` / `description` / `instructions` если текст не размечен.

Поле верхнего уровня `inn` можно показать под названием (как «МНН: …»).

## Откуда текст

Секции собираются из `description` + `instructions` в БД (ГРЛС / Vidal).  
Если у препарата в базе только «МНН + источник + связанные болезни» (как у части ГРЛС), спойлеров будет мало — это данные, не баг UI.

Полный Vidal появляется после импорта с деталями:

```bash
python manage.py parse_vidal_drugs --resume --fetch-details
python manage.py import_parsed_catalog --drugs-only
```
