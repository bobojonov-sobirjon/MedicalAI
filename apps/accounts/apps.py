from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "01. Аккаунты"

    def ready(self) -> None:
        from .russian_labels import apply_custom_user_russian_labels

        apply_custom_user_russian_labels()

