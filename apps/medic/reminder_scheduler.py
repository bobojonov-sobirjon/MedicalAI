from __future__ import annotations

import logging
import os
import threading
import time

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .models import NotificationEvent

logger = logging.getLogger(__name__)


def _should_start_thread() -> bool:
    """
    Avoid double-start under Django autoreloader.
    """
    if os.environ.get("RUN_MAIN") == "true":
        return True
    # When autoreloader is off, RUN_MAIN may be missing.
    return bool(getattr(settings, "DEBUG", False))


def start_reminder_scheduler(*, interval_s: int = 20) -> None:
    """
    Start a lightweight background poller that creates due reminder notifications.

    NOTE: This is a simple in-process scheduler suitable for development / single instance.
    For multi-instance production, use a proper task scheduler (Celery/Beat, cron, etc.).
    """
    enabled = str(getattr(settings, "ENABLE_REMINDER_SCHEDULER", "true")).lower() in ("1", "true", "yes")
    if not enabled:
        return
    if not _should_start_thread():
        return

    if getattr(start_reminder_scheduler, "_started", False):  # type: ignore[attr-defined]
        return
    setattr(start_reminder_scheduler, "_started", True)  # type: ignore[attr-defined]

    def loop() -> None:
        logger.info("Reminder scheduler started (interval=%ss)", interval_s)
        while True:
            try:
                close_old_connections()
                now = timezone.now()
                # Parents that could have due children: event_at within next 24h and not too old
                parents = (
                    NotificationEvent.objects.filter(
                        kind=NotificationEvent.Kind.REMINDER,
                        parent__isnull=True,
                        event_at__isnull=False,
                        event_at__lte=now + timezone.timedelta(days=1),
                        event_at__gte=now - timezone.timedelta(days=2),
                    )
                    .only("id", "recipient_id")
                    .order_by("-created_at")[:500]
                )
                # Group by recipient and run ensure logic by importing lazily to avoid circular imports
                by_user: dict[int, list[int]] = {}
                for p in parents:
                    by_user.setdefault(int(p.recipient_id), []).append(int(p.id))

                if by_user:
                    from django.contrib.auth import get_user_model
                    from .views import _ensure_reminder_children

                    User = get_user_model()
                    for uid in by_user.keys():
                        u = User.objects.filter(id=uid).first()
                        if u:
                            _ensure_reminder_children(u)
            except Exception as exc:  # pragma: no cover
                logger.warning("Reminder scheduler tick failed: %s", exc)
            time.sleep(interval_s)

    t = threading.Thread(target=loop, name="reminder-scheduler", daemon=True)
    t.start()

