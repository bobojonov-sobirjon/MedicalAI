# MedicAI — GET /api/catalog/drugs/ (pagination + filters)

**Base:** `http://85.198.101.179:8007/api/`  
**Auth:** не обязателен.

---

## Endpoint

`GET /api/catalog/drugs/`

Список теперь **с пагинацией**. Вложенные `diseases` по умолчанию **не** отдаются (чтобы ответ не был 12+ MB).  
Полный текст + список болезней — в detail: `GET /api/catalog/drugs/{id}/`.

---

## Pagination

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `page` | `1` | Номер страницы (с 1) |
| `page_size` | `50` | Размер страницы (1–100) |
| `limit` | — | Альтернатива `page_size` |
| `offset` | — | Смещение (если используете limit/offset) |

### Пример

`GET /api/catalog/drugs/?page=1&page_size=50`

### Response

```json
{
  "count": 13373,
  "page": 1,
  "page_size": 50,
  "total_pages": 268,
  "next": "http://85.198.101.179:8007/api/catalog/drugs/?page=2&page_size=50",
  "previous": null,
  "results": [
    {
      "id": 3445,
      "name": "Валвир",
      "description_preview": "Противовирусный препарат...",
      "instructions_preview": "Дозу определяет врач...",
      "dosage": "",
      "image": null,
      "rating": "0.00",
      "diseases_count": 60,
      "in_my_cabinet": false,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

---

## Filters

| Параметр | Пример | Описание |
|----------|--------|----------|
| `q` | `?q=валвир` | Поиск по названию / описанию / инструкции |
| `letter` | `?letter=А` | Первая буква названия |
| `disease_id` | `?disease_id=154` | Препараты, связанные с болезнью |
| `ordering` | `?ordering=-rating` | `name`, `-name`, `rating`, `-rating`, `created_at`, `-created_at` |
| `has_diseases` | `?has_diseases=true` | Только с болезнями / без (`false`) |
| `has_image` | `?has_image=true` | Только с картинкой / без |
| `include_diseases` | `?include_diseases=true` | Вложить полный `diseases` (тяжёлый режим, не для списка) |

### Примеры

```http
GET /api/catalog/drugs/?page=1&page_size=30
GET /api/catalog/drugs/?q=ацикловир&page=1
GET /api/catalog/drugs/?letter=В&ordering=name
GET /api/catalog/drugs/?disease_id=154&page=1&page_size=20
GET /api/catalog/drugs/?ordering=-rating&has_diseases=true
```

---

## Flutter

1. Список: `GET /catalog/drugs/?page=&page_size=` → показывать `results`.
2. Подгрузка: `page++` пока `next != null`.
3. Тап по препарату: `GET /catalog/drugs/{id}/` → полный `description` + `diseases` / `related_diseases`.

---

## Detail (без изменений)

`GET /api/catalog/drugs/{id}/` — полный объект с `diseases` и `related_diseases` (круговая навигация).
