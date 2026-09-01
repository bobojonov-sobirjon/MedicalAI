from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from rest_framework import serializers

from .models import CustomUser


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        allow_null=False,
        allow_blank=False,
        help_text="Эл. почта пользователя (обязательно). Должна быть уникальной.",
    )
    phone_number = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Телефон пользователя (необязательно). Если указан — должен быть уникальным.",
    )
    username = serializers.CharField(
        required=True,
        allow_null=False,
        allow_blank=False,
        help_text="Логин (обязательно). Уникальное имя пользователя.",
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=6,
        help_text="Пароль (минимум 6 символов).",
    )
    first_name = serializers.CharField(required=False, allow_blank=True, help_text="Имя (необязательно).")
    last_name = serializers.CharField(required=False, allow_blank=True, help_text="Фамилия (необязательно).")

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip()
        phone = (attrs.get("phone_number") or "").strip()
        username = (attrs.get("username") or "").strip()

        if not email:
            raise serializers.ValidationError({"email": "Email обязателен."})
        if not username:
            raise serializers.ValidationError({"username": "Username обязателен."})

        if email:
            attrs["email"] = email.lower()
        if phone:
            attrs["phone_number"] = phone
        if username:
            attrs["username"] = username

        # Proactive uniqueness checks to return 400 instead of 500 on DB constraint errors.
        errors = {}
        if attrs.get("email") and CustomUser.objects.filter(email__iexact=attrs["email"]).exists():
            errors["email"] = "Пользователь с таким email уже существует."
        if attrs.get("username") and CustomUser.objects.filter(username=attrs["username"]).exists():
            errors["username"] = "Пользователь с таким username уже существует."
        if attrs.get("phone_number") and CustomUser.objects.filter(phone_number=attrs["phone_number"]).exists():
            errors["phone_number"] = "Пользователь с таким телефоном уже существует."
        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_password(self, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Пароль должен содержать минимум 1 букву и 1 цифру (ТЗ §7.3).")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        try:
            user = CustomUser.objects.create_user(**validated_data)
        except IntegrityError:
            # Safety net: if a concurrent request created the same user, map to 400.
            raise serializers.ValidationError(
                {"detail": "Пользователь с такими данными уже существует. Измените email/username/телефон."}
            )
        user.set_password(password)
        user.save(update_fields=["password"])
        from apps.billing.services import grant_welcome_trial

        grant_welcome_trial(user)
        return user


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        required=True,
        help_text="Логин: username (логин) или email (почта) или phone_number (телефон).",
    )
    password = serializers.CharField(required=True, write_only=True, help_text="Пароль.")

    def validate(self, attrs):
        identifier = attrs["identifier"].strip()
        password = attrs["password"]

        # Try username/email/phone
        user = authenticate(username=identifier, password=password)
        if user is None:
            # fallback: if identifier is email or phone, try to find username
            try:
                u = CustomUser.objects.get(email__iexact=identifier)
                user = authenticate(username=u.username, password=password)
            except CustomUser.DoesNotExist:
                user = None
            if user is None:
                try:
                    u = CustomUser.objects.get(phone_number=identifier)
                    user = authenticate(username=u.username, password=password)
                except CustomUser.DoesNotExist:
                    user = None

        if user is None:
            raise serializers.ValidationError("Неверный логин или пароль.")
        if not user.is_active:
            raise serializers.ValidationError("Пользователь заблокирован.")
        attrs["user"] = user
        return attrs


class UserMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "id",
            "username",
            "email",
            "phone_number",
            "nickname",
            "first_name",
            "last_name",
            "avatar",
            "gender",
            "city",
            "date_of_birth",
            "height_cm",
            "weight_kg",
            "chronic_diseases",
            "had_covid",
            "useful_tips_subscribed",
            "active_profile_id",
        )
        read_only_fields = ("id", "email", "phone_number", "active_profile_id")


class UserUpdateSerializer(serializers.ModelSerializer):
    pin_code = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True, max_length=12)

    class Meta:
        model = CustomUser
        fields = (
            "first_name",
            "last_name",
            "nickname",
            "avatar",
            "phone_number",
            "username",
            "gender",
            "city",
            "date_of_birth",
            "height_cm",
            "weight_kg",
            "chronic_diseases",
            "had_covid",
            "useful_tips_subscribed",
            "pin_code",
        )
        extra_kwargs = {
            "first_name": {"help_text": "Имя."},
            "last_name": {"help_text": "Фамилия."},
            "nickname": {"help_text": "Ник (латиница и цифры)."},
            "avatar": {"help_text": "Аватар (multipart)."},
            "phone_number": {"help_text": "Номер телефона."},
            "username": {"help_text": "Логин (уникальный)."},
            "gender": {"help_text": "male | female | other"},
            "city": {"help_text": "Город проживания."},
            "date_of_birth": {"help_text": "Дата рождения (YYYY-MM-DD)."},
            "height_cm": {"help_text": "Рост в сантиметрах."},
            "weight_kg": {"help_text": "Вес в килограммах (опционально)."},
            "chronic_diseases": {"help_text": "Хронические заболевания (текст)."},
            "had_covid": {"help_text": "null | true | false"},
            "useful_tips_subscribed": {"help_text": "Подписка на полезное (ТЗ §7.12.2)."},
        }

    def validate_username(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("Username обязателен.")
        if len(v) > 150:
            raise serializers.ValidationError("Username слишком длинный.")
        if CustomUser.objects.filter(username=v).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError("Пользователь с таким username уже существует.")
        return v

    def validate_pin_code(self, value: str | None) -> str:
        if value is None:
            return ""
        v = str(value).strip()
        if not v:
            return ""
        if not v.isdigit() or not (4 <= len(v) <= 8):
            raise serializers.ValidationError("Пин-код: 4–8 цифр.")
        return v

    def update(self, instance, validated_data):
        pin = validated_data.pop("pin_code", None)
        user = super().update(instance, validated_data)
        if pin:
            user.pin_code_hash = make_password(pin)
            user.save(update_fields=["pin_code_hash"])
        return user


class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, help_text="Эл. почта аккаунта; код будет отправлен на этот адрес.")


class ForgotPasswordVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, help_text="Та же эл. почта, что и на шаге отправки кода.")
    code = serializers.CharField(required=True, help_text="6-значный код из письма.")

    def validate_code(self, value: str) -> str:
        v = (value or "").strip()
        if not v.isdigit() or len(v) != 6:
            raise serializers.ValidationError("Код должен состоять ровно из 6 цифр.")
        return v


class ForgotPasswordResetSerializer(serializers.Serializer):
    reset_token = serializers.CharField(
        required=True,
        help_text="Токен из POST /api/auth/password/forgot/verify/ после проверки кода.",
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=6,
        help_text="Новый пароль (ТЗ §7.3: минимум 6 символов, буквы и цифры).",
    )

    def validate_new_password(self, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Пароль должен содержать минимум 1 букву и 1 цифру.")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, help_text="Текущий пароль.")
    new_password = serializers.CharField(write_only=True, min_length=6, help_text="Новый пароль (ТЗ §7.3: минимум 6 символов, буквы и цифры).")

    def validate_new_password(self, value: str) -> str:
        # TZ §7.3: length and presence of letters and digits
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Пароль должен содержать минимум 1 букву и 1 цифру.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": "Неверный текущий пароль."})
        return attrs

