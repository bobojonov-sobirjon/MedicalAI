# Frontend: Обратная связь (Отправить)

## UI (mijoz talabi)

| UI | Qiymat |
|----|--------|
| Tugma | **Отправить** (не «Сохранить») |
| Maydon 1 | **Почта обратной связи** → API `email` |
| Maydon 2 | **Письмо / Сообщение** → API `message` |

## API

`POST /api/support/feedback/`

Auth: `Authorization: Bearer <access_token>`

### Body

```json
{
  "email": "user@example.com",
  "message": "Текст обращения…",
  "subject": "Обратная связь"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `email` | **yes** | Почта обратной связи (Reply-To) |
| `message` | **yes** | Текст письма |
| `subject` | no | Тема; default `Обратная связь` |

### Response `201`

```json
{
  "ok": true,
  "detail": "Сообщение отправлено.",
  "ticket_id": 12
}
```

### Backend behavior

1. Yozuv `FeedbackTicket` jadvaliga saqlanadi (admin da ko‘rinadi).
2. Email yuboriladi: **`FEEDBACK_TO_EMAIL`** = `cybertime.syst@gmail.com` (default).
3. `Reply-To` = foydalanuvchi kiritgan `email`.

## Flutter qisqa

```dart
await api.post('/support/feedback/', data: {
  'email': feedbackEmailController.text.trim(),
  'message': messageController.text.trim(),
});
// button label: Отправить
```
