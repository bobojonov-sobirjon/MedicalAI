# Frontend: Аптечка ↔ справочник лекарств и болезней

Аптечка **не хранит** описание лекарства и список болезней отдельно.
Всё подгружается из `catalog.Drug` и связанных `catalog.Disease`.

## Добавить в аптечку

1. Найти препарат в справочнике:

`GET /api/catalog/drugs/?q=Нурофен&page=1&page_size=20`

2. Добавить по `drug_id`:

`POST /api/me/cabinet/items/`

```json
{
  "drug_id": 123,
  "expires_at": "2027-01-01",
  "note": "Домашняя аптечка"
}
```

Допускается алиас `"drug": 123` вместо `drug_id`.

Без `drug_id` запись **не создаётся** (кроме случая, когда `custom_name` точно находится в справочнике).

## Ответ списка / карточки

`GET /api/me/cabinet/items/`

Каждый элемент:

```json
{
  "id": 1,
  "drug_id": 123,
  "catalog_drug_id": 123,
  "display_name": "Нурофен",
  "drug_detail": {
    "id": 123,
    "name": "Нурофен",
    "description": "...из БД...",
    "description_preview": "...",
    "instructions": "...из БД...",
    "instructions_preview": "...",
    "dosage": "...",
    "image": "...",
    "rating": "0.00",
    "diseases": [
      { "id": 10, "name": "Головная боль", "description_preview": "..." }
    ],
    "related_diseases": [ "...то же..." ]
  },
  "diseases": [
    { "id": 10, "name": "Головная боль", "description_preview": "..." }
  ],
  "expires_at": "2027-01-01",
  "note": "...",
  "photo": null,
  "created_at": "...",
  "updated_at": "..."
}
```

UI должен показывать:

- название / описание / инструкцию из `drug_detail`
- связанные болезни из `diseases` или `drug_detail.diseases`

Не дублировать эти тексты локально в аптечке.

## Распознавание по фото

`POST /api/me/cabinet/recognize/`

- Ищет совпадение **только** в справочнике лекарств
- Новые «пустые» препараты в БД больше не создаются
- Если `catalog_match=false` — предложите пользователю выбрать препарат из `GET /api/catalog/drugs/?q=`

## Синхронизация старых записей

На сервере (если были записи только с `custom_name`):

```bash
python manage.py sync_cabinet_drugs
```
