from __future__ import annotations

from django.contrib.auth import authenticate
from django.db import IntegrityError
from rest_framework import serializers

from .models import CustomUser


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        allow_null=False,
        allow_blank=False,
        help_text="Email пользователя (обязательно). Должен быть уникальным.",
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
        help_text="Username (обязательно). Уникальный логин пользователя.",
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
        return user


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        required=True,
        help_text="Логин: username или email или phone_number.",
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
            "first_name",
            "last_name",
            "avatar",
            "nickname",
            "gender",
            "city",
            "date_of_birth",
            "height_cm",
            "weight_kg",
        )
        read_only_fields = ("id", "username", "email", "phone_number")


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = (
            "first_name",
            "last_name",
            "avatar",
            "phone_number",
            "nickname",
            "gender",
            "city",
            "date_of_birth",
            "height_cm",
            "weight_kg",
        )
        extra_kwargs = {
            "first_name": {"help_text": "First name."},
            "last_name": {"help_text": "Last name / surname."},
            "avatar": {"help_text": "Avatar image (multipart)."},
            "phone_number": {"help_text": "Phone number."},
            "nickname": {"help_text": "Display nickname."},
            "gender": {"help_text": "male | female | other"},
            "city": {"help_text": "City name."},
            "date_of_birth": {"help_text": "Date of birth (YYYY-MM-DD)."},
            "height_cm": {"help_text": "Height in cm."},
            "weight_kg": {"help_text": "Weight in kg (optional)."},
        }

    def validate_nickname(self, value):
        if value and len(value) > 64:
            raise serializers.ValidationError("Ник слишком длинный.")
        return (value or "").strip()


class ForgotPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, help_text="Email аккаунта; код будет отправлен на этот адрес.")


class ForgotPasswordVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, help_text="Тот же email, что и на шаге отправки кода.")
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

