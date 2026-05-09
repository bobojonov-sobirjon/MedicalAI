"""Push NotificationEvent updates to the user's WebSocket group (Django Channels)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

if TYPE_CHECKING:
    from .models import NotificationEvent


def notification_to_dict(instance: "NotificationEvent") -> dict:
    return {
        "id": instance.id,
        "kind": instance.kind,
        "title": instance.title,
        "body": instance.body,
        "link_url": instance.link_url or "",
        "read_at": instance.read_at.isoformat() if instance.read_at else None,
        "event_at": instance.event_at.isoformat() if instance.event_at else None,
        "notify_at": instance.notify_at.isoformat() if getattr(instance, "notify_at", None) else None,
        "parent_id": getattr(instance, "parent_id", None),
        "subject_user_id": getattr(instance, "subject_user_id", None),
        "subject_user_label": instance.subject_user_label or "",
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
    }


def group_name_for_user(user_id: int) -> str:
    return f"user_{user_id}_notifications"


def broadcast_notification_event(instance: "NotificationEvent", *, created: bool) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        group_name_for_user(instance.recipient_id),
        {
            "type": "notify.event",
            "created": created,
            "notification": notification_to_dict(instance),
        },
    )
