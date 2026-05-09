from django.apps import AppConfig


class MedicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.medic"
    verbose_name = "Сервисы (уведомления, контент, поддержка)"

    def ready(self) -> None:
        from . import receivers  # noqa: F401
        from . import signals  # noqa: F401
        from .reminder_scheduler import start_reminder_scheduler

        # Real-time reminders (simple in-process poller).
        start_reminder_scheduler()
