# История болезней: форма «Добавить запись» ↔ API

## Важно

**POST не ищет препараты.**  
На форме поиск = отдельные **GET**. Сохранение = **POST** с уже выбранными `id`.

```
UI «Препараты» → GET поиск → пользователь выбирает → POST drug_ids: [123, …]
```

RuTronix здесь **не используется** (только OCR/AI в других местах).

---

## Поля экрана → API

| UI (скрин) | GET (поиск / список) | POST / PATCH поле |
|------------|----------------------|-------------------|
| Профиль | `GET /api/me/profiles/` (или уже загруженный список) | `subject_user_id` |
| Дата начала болезни | — | `date_of_illness` (`YYYY-MM-DD`) |
| Название болезни | `GET /api/catalog/diseases/?q=` | `disease_id` |
| Симптомы | — | `symptoms` |
| **Препараты** | **`GET /api/me/disease-records/drugs/?q=Креон`** | **`drug_ids`** |
| Посещение врача (+ …) | после создания записи | `POST /api/me/disease-records/doctor-visits/` |

Создание записи:

`POST /api/me/disease-records/`  
Auth: Bearer. Body: JSON или `multipart/form-data`.

```json
{
  "subject_user_id": 1,
  "date_of_illness": "2022-03-01",
  "disease_id": 55,
  "symptoms": "…",
  "drug_ids": [123, 124],
  "title": ""
}
```

`drug_ids` также можно так: `"123,124"` (multipart).

---

## Препараты — какой GET

### Рекомендуется для этой формы

```http
GET /api/me/disease-records/drugs/?q=Креон
Authorization: Bearer …
```

Ответ — **JSON array** (как у болезней):

```json
[
  { "id": 123, "name": "Креон 10000", "dosage": "…" },
  { "id": 124, "name": "Креон 25000", "dosage": "…" }
]
```

Без `q` — **весь** лёгкий каталог (для локального фильтра в модалке).

Путь под `/api/me/disease-records/` → работает и при `history_only` (бесплатная история).

### Эквивалент раздела «Лекарства»

```http
GET /api/catalog/drugs/?q=Креон&page=1&page_size=50
```

Ответ: `{ "results": [ … ], "count": … }` — берите `results`.  
Либо `GET /api/catalog/drugs/?picker=1` → array.

Оба источника — **одна БД**. В «Лекарства» Креон есть ⇒ тем же `q` он должен быть и в истории.

---

## Запрещено

| Нельзя | Почему |
|--------|--------|
| Ждать список препаратов **внутри** POST | POST только сохраняет |
| `GET /catalog/diseases/{id}/` → `drugs` | Неполный список (только связанные) |
| `GET /catalog/drugs/` page=1 без `q` + локальный фильтр | ~50 шт., Креон может отсутствовать |
| RuTronix / LLM как справочник | Каталог только из БД |

---

## Flutter

```dart
// 1) Пикер «Препараты»
final res = await api.get(
  '/me/disease-records/drugs/',
  queryParameters: {'q': query.trim()}, // или без q — полный список
);
final items = res.data as List; // [{id, name, dosage}, ...]

// 2) Сохранить запись
await api.post('/me/disease-records/', data: {
  'subject_user_id': profileId,
  'date_of_illness': '2022-03-01',
  'disease_id': diseaseId,
  'symptoms': symptoms,
  'drug_ids': selectedDrugIds, // List<int>
});
```

---

## Чеклист FE

- [ ] «Препараты» → `GET /api/me/disease-records/drugs/` (или catalog/drugs с `q` / `picker=1`)
- [ ] «Креон» в истории = те же id, что в «Лекарства»
- [ ] POST шлёт `drug_ids`, а не имена
- [ ] Визиты врача — отдельный POST после создания записи
