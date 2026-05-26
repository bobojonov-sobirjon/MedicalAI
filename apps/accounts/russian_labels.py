"""Русские подписи полей CustomUser (наследие AbstractUser) для админки."""

from __future__ import annotations

from django.contrib.auth import get_user_model


def apply_custom_user_russian_labels() -> None:
    User = get_user_model()
    labels = {
        "username": "Логин",
        "password": "Пароль",
        "first_name": "Имя",
        "last_name": "Фамилия",
        "email": "Эл. почта",
        "is_active": "Активен",
        "is_staff": "Персонал",
        "is_superuser": "Суперпользователь",
        "last_login": "Последний вход",
        "date_joined": "Дата регистрации",
        "groups": "Группы",
        "user_permissions": "Права доступа",
    }
    for name, label in labels.items():
        try:
            User._meta.get_field(name).verbose_name = label
        except Exception:
            pass
