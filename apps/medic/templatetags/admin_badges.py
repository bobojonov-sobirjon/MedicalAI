from __future__ import annotations

from django import template
from django.urls import reverse
from django.utils import timezone

from apps.medic.models import DrugReview, FeedbackTicket, PsychologyInquiry

register = template.Library()


@register.simple_tag
def pending_drug_reviews_count() -> int:
    return DrugReview.objects.filter(status=DrugReview.Status.PENDING).count()


@register.simple_tag
def admin_notifications() -> dict:
    """
    Returns a dict for rendering a global admin bell:
    {
      "total": int,
      "items": [{"key","title","count","url"}...]
    }
    """
    # Reviews pending
    reviews_cnt = DrugReview.objects.filter(status=DrugReview.Status.PENDING).count()
    # Psychology inquiries (status field is free-form; use "new" as default)
    psych_cnt = PsychologyInquiry.objects.filter(status="new").count()
    # Feedback: no status field; show last 7 days as "new"
    since = timezone.now() - timezone.timedelta(days=7)
    fb_cnt = FeedbackTicket.objects.filter(created_at__gte=since).count()

    items = [
        {
            "key": "drug_reviews",
            "title": "Отзывы на лекарства (на модерации)",
            "count": reviews_cnt,
            "url": reverse("admin:medic_drugreview_changelist") + "?status__exact=pending",
        },
        {
            "key": "psychology",
            "title": "Вопросы психологу (новые)",
            "count": psych_cnt,
            "url": reverse("admin:medic_psychologyinquiry_changelist") + "?status__exact=new",
        },
        {
            "key": "feedback",
            "title": "Обратная связь (за 7 дней)",
            "count": fb_cnt,
            "url": reverse("admin:medic_feedbackticket_changelist"),
        },
    ]
    total = sum(int(x["count"]) for x in items)
    return {"total": total, "items": items}

