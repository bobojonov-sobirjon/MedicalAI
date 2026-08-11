from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import FeedbackTicket, NotificationEvent, PsychologyInquiry
from .ws_broadcast import broadcast_notification_event

logger = logging.getLogger(__name__)


@receiver(post_save, sender=FeedbackTicket)
def _feedback_email(sender, instance: FeedbackTicket, created: bool, **kwargs) -> None:
    """Отправка обращения на почту поддержки (cybertime.syst@gmail.com по умолчанию)."""
    if not created:
        return
    to = (getattr(settings, "FEEDBACK_TO_EMAIL", "") or "cybertime.syst@gmail.com").strip()
    reply_to = (instance.email or "").strip() or None
    user = instance.user
    who = ""
    if user is not None:
        who = user.get_full_name() or user.username or str(user.pk)
    subject = (instance.subject or "").strip() or "Обратная связь"
    mail_subject = f"[MedicAI] {subject}" + (f" — {who}" if who else "")
    body_lines = [
        f"От: {who or '—'}",
        f"Почта обратной связи: {reply_to or '—'}",
        f"Тема: {subject}",
        "",
        instance.message,
    ]
    try:
        msg = EmailMessage(
            mail_subject,
            "\n".join(body_lines),
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@medicalai.local"),
            [to],
        )
        if reply_to:
            msg.reply_to = [reply_to]
        msg.send(fail_silently=False)
        logger.info("Feedback email sent ticket_id=%s to=%s", instance.pk, to)
    except Exception as exc:  # pragma: no cover
        logger.warning("Feedback email failed ticket_id=%s: %s", instance.pk, exc)


@receiver(post_save, sender=PsychologyInquiry)
def _psych_email(sender, instance: PsychologyInquiry, created: bool, **kwargs) -> None:
    if not created:
        return
    to = getattr(settings, "PSYCHOLOGY_EMAIL", "psychology@medic-ai.ru")
    user = instance.user
    reply_to = (user.email or "").strip() or None
    subject = f"[MedicAI] Вопрос психологу от {user.get_full_name() or user.username}"
    body = instance.message
    try:
        msg = EmailMessage(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@medicalai.local"),
            [to],
        )
        if reply_to:
            msg.reply_to = [reply_to]
        msg.send(fail_silently=False)
    except Exception as exc:  # pragma: no cover
        logger.warning("Psychology email failed: %s", exc)


@receiver(post_save, sender=NotificationEvent)
def _push_notification_ws(sender, instance: NotificationEvent, created: bool, **kwargs) -> None:
    try:
        broadcast_notification_event(instance, created=created)
    except Exception as exc:  # pragma: no cover
        logger.warning("WebSocket notification broadcast failed: %s", exc)
