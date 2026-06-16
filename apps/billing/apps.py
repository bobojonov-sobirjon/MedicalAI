from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    verbose_name = "07. Оплата и подписки"

    def ready(self) -> None:
        from .subscription_scheduler import start_subscription_scheduler

        start_subscription_scheduler()
