from __future__ import annotations

import logging
import os
import threading
import time

from django.conf import settings
from django.db import close_old_connections

from .services import process_subscription_lifecycle_tick

logger = logging.getLogger(__name__)


def _should_start_thread() -> bool:
    if os.environ.get("RUN_MAIN") == "true":
        return True
    return bool(getattr(settings, "DEBUG", False))


def start_subscription_scheduler(*, interval_s: int = 3600) -> None:
    """Проверка истечения trial/подписок и напоминания (раз в час)."""
    enabled = str(getattr(settings, "ENABLE_SUBSCRIPTION_SCHEDULER", "true")).lower() in ("1", "true", "yes")
    if not enabled:
        return
    if not _should_start_thread():
        return
    if getattr(start_subscription_scheduler, "_started", False):  # type: ignore[attr-defined]
        return
    setattr(start_subscription_scheduler, "_started", True)  # type: ignore[attr-defined]

    def loop() -> None:
        logger.info("Subscription scheduler started (interval=%ss)", interval_s)
        while True:
            try:
                close_old_connections()
                process_subscription_lifecycle_tick()
            except Exception as exc:  # pragma: no cover
                logger.warning("Subscription scheduler tick failed: %s", exc)
            time.sleep(interval_s)

    t = threading.Thread(target=loop, name="subscription-scheduler", daemon=True)
    t.start()
