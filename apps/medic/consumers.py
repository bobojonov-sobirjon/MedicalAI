"""WebSocket: real-time notification feed for authenticated users."""

from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from .models import NotificationEvent
from .ws_broadcast import group_name_for_user, notification_to_dict


class NotificationConsumer(AsyncWebsocketConsumer):
    """Client: ``ws(s)://<host>/ws/notifications/?token=<JWT_access>``"""

    async def connect(self) -> None:
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4001)
            return
        self._uid = int(user.pk)
        self.group_name = group_name_for_user(self._uid)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._recent_notifications()
        await self.send(
            text_data=json.dumps({"op": "hello", "notifications": snapshot}, default=str)
        )

    async def disconnect(self, code: int) -> None:
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notify_event(self, event: dict) -> None:
        await self.send(
            text_data=json.dumps(
                {
                    "op": "notification",
                    "created": event.get("created", False),
                    "notification": event.get("notification"),
                },
                default=str,
            )
        )

    @database_sync_to_async
    def _recent_notifications(self, limit: int = 30) -> list[dict]:
        qs = (
            NotificationEvent.objects.filter(recipient_id=self._uid)
            .order_by("-created_at")[:limit]
        )
        return [notification_to_dict(x) for x in qs]
