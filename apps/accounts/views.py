from __future__ import annotations

import logging
from django.contrib.auth.hashers import check_password
from django.core import signing
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, PasswordResetCode, SocialAccount
from .password_reset import issue_password_reset_code
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserMeSerializer,
    UserUpdateSerializer,
    PasswordChangeSerializer,
    ForgotPasswordRequestSerializer,
    ForgotPasswordVerifySerializer,
    ForgotPasswordResetSerializer,
)
from .services import SocialAuthService
from .services import FirebaseAuthService
from .mail import send_password_reset_email
from .reset_session import create_reset_session_token, parse_reset_session_token


logger = logging.getLogger(__name__)


def _tokens_for_user(user: CustomUser) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Регистрация пользователя",
        description=(
            "Создаёт новый аккаунт.\n\n"
            "Обязательные поля: `email` и `username`.\n"
            "Возвращает профиль пользователя + пару JWT токенов."
        ),
        request=RegisterSerializer,
        responses={
            201: inline_serializer(
                name="RegisterResponse",
                fields={
                    "user": UserMeSerializer(),
                    "tokens": inline_serializer(
                        name="TokenPair",
                        fields={"access": serializers.CharField(), "refresh": serializers.CharField()},
                    ),
                },
            )
        },
        examples=[
            OpenApiExample(
                "Регистрация",
                value={
                    "email": "user@example.com",
                    "username": "user123",
                    "password": "secret123",
                    "first_name": "Ali",
                    "last_name": "Vali",
                },
            )
        ],
    )
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        return Response({"user": UserMeSerializer(user).data, "tokens": _tokens_for_user(user)}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Вход (username/email/phone + пароль)",
        description="Вход по `identifier` (username/email/phone_number) + `password`. Возвращает профиль + пару JWT токенов.",
        request=LoginSerializer,
        responses={
            200: inline_serializer(
                name="LoginResponse",
                fields={
                    "user": UserMeSerializer(),
                    "tokens": inline_serializer(
                        name="TokenPair2",
                        fields={"access": serializers.CharField(), "refresh": serializers.CharField()},
                    ),
                },
            )
        },
        examples=[OpenApiExample("Login", value={"identifier": "user@example.com", "password": "secret123"})],
    )
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.validated_data["user"]
        return Response({"user": UserMeSerializer(user).data, "tokens": _tokens_for_user(user)})


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Обновить access токен",
        description="Используйте `refresh` токен, чтобы получить новый `access` токен.",
        request=inline_serializer(
            name="RefreshRequest",
            fields={"refresh": serializers.CharField()},
        ),
        responses=inline_serializer(
            name="RefreshResponse",
            fields={"access": serializers.CharField()},
        ),
        examples=[OpenApiExample("Refresh", value={"refresh": "<refresh_token>"})],
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Поле refresh обязательно."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(refresh_token)
            return Response({"access": str(refresh.access_token)})
        except Exception:
            return Response({"detail": "Неверный refresh токен."}, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["User Details"],
        summary="Получить профиль текущего пользователя",
        description="Возвращает профиль текущего пользователя (ник, пол, город, дата рождения, рост, вес и т.д.).",
        responses=UserMeSerializer,
    )
    def get(self, request):
        return Response(UserMeSerializer(request.user, context={"request": request}).data)

    @extend_schema(
        tags=["User Details"],
        summary="Обновить профиль",
        description="Обновляет поля профиля (ФИО, ник, пол, город, дата рождения, рост, вес). Для аватара используйте multipart/form-data. Смена пароля: POST /api/auth/password/change/ (см. ТЗ §7.7 / §7.5).",
        request=UserUpdateSerializer,
        responses=UserMeSerializer,
    )
    def patch(self, request):
        s = UserUpdateSerializer(instance=request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        user = s.save()
        return Response(UserMeSerializer(user, context={"request": request}).data)


class SocialLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Соц. вход (VK/Google/Apple)",
        description=(
            "Единый endpoint для входа через соцсети.\n\n"
            "- Google/Apple (Firebase): отправьте `id_token` из Firebase Auth.\n"
            "- VK: отправьте `code` (рекомендуется) или `access_token`, а также опционально `platform` (android/ios).\n\n"
            "Возвращает профиль пользователя + пару JWT токенов."
        ),
        request=inline_serializer(
            name="SocialLoginRequest",
            fields={
                "provider": serializers.ChoiceField(choices=["vk", "google", "apple"]),
                "platform": serializers.ChoiceField(choices=["android", "ios"], required=False),
                "id_token": serializers.CharField(required=False),
                "code": serializers.CharField(required=False),
                "access_token": serializers.CharField(required=False),
            },
        ),
        responses={
            200: inline_serializer(
                name="SocialLoginResponse",
                fields={
                    "user": UserMeSerializer(),
                    "tokens": inline_serializer(
                        name="TokenPair3",
                        fields={"access": serializers.CharField(), "refresh": serializers.CharField()},
                    ),
                },
            )
        },
        examples=[
            OpenApiExample("Google (Firebase)", value={"provider": "google", "id_token": "<firebase_id_token>"}),
            OpenApiExample("Apple (Firebase)", value={"provider": "apple", "id_token": "<firebase_id_token>"}),
            OpenApiExample("VK Android (code)", value={"provider": "vk", "platform": "android", "code": "<vk_code>"}),
            OpenApiExample("VK iOS (code)", value={"provider": "vk", "platform": "ios", "code": "<vk_code>"}),
            OpenApiExample("VK (access)", value={"provider": "vk", "platform": "android", "access_token": "<vk_access_token>"}),
        ],
    )
    def post(self, request):
        provider = (request.data.get("provider") or "").strip().lower()
        try:
            if provider in (SocialAccount.Provider.GOOGLE, SocialAccount.Provider.APPLE):
                # Firebase flow: mobile sends Firebase Auth ID token for Google/Apple sign-in
                token = request.data.get("id_token") or ""
                profile = FirebaseAuthService.verify_id_token(token)
            elif provider == SocialAccount.Provider.VK:
                code = request.data.get("code")
                access_token = request.data.get("access_token")
                platform = (request.data.get("platform") or "").strip().lower() or None
                if code:
                    profile = SocialAuthService.verify_vk(code, is_code=True, platform=platform)
                elif access_token:
                    profile = SocialAuthService.verify_vk(access_token, is_code=False, platform=platform)
                else:
                    return Response({"detail": "Нужно передать code или access_token."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({"detail": "provider должен быть одним из: vk, google, apple"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "Не удалось проверить токен социальной авторизации."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            link = SocialAccount.objects.select_for_update().filter(
                provider=profile.provider, provider_user_id=profile.provider_user_id
            ).select_related("user").first()

            if link:
                user = link.user
            else:
                # Try to match by email if provided.
                user = None
                if profile.email:
                    user = CustomUser.objects.filter(email__iexact=profile.email).first()

                if user is None:
                    username = profile.email or f"{profile.provider}_{profile.provider_user_id}"
                    user = CustomUser.objects.create_user(
                        username=username,
                        email=(profile.email.lower() if profile.email else None),
                        first_name=profile.first_name or "",
                        last_name=profile.last_name or "",
                    )
                    user.set_unusable_password()
                    user.save(update_fields=["password"])

                SocialAccount.objects.create(
                    user=user, provider=profile.provider, provider_user_id=profile.provider_user_id
                )

        return Response({"user": UserMeSerializer(user).data, "tokens": _tokens_for_user(user)})


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Сменить пароль (пользователь авторизован)",
        description=(
            "ТЗ §7.7: смена пароля в профиле (старый + новый). "
            "Если пароль забыли: POST /api/auth/password/forgot/request/, /forgot/verify/, /forgot/reset/ (код на email, ТЗ §7.5)."
        ),
        request=PasswordChangeSerializer,
        responses={200: inline_serializer(name="PasswordChangeOk", fields={"detail": serializers.CharField()})},
        examples=[OpenApiExample("Change password", value={"old_password": "oldsecret", "new_password": "newsecret123"})],
    )
    def post(self, request):
        s = PasswordChangeSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        user = request.user
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Пароль успешно изменён."})


class ForgotPasswordRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Забыли пароль — отправить код на email (ТЗ §7.5)",
        description=(
            "Send only `email`. If an active account with this email exists, a 6-digit code is emailed. "
            "Same generic message if the account does not exist (privacy)."
        ),
        request=ForgotPasswordRequestSerializer,
        responses={200: inline_serializer(name="ForgotRequestOk", fields={"detail": serializers.CharField()})},
        examples=[OpenApiExample("Request code", value={"email": "user@example.com"})],
    )
    def post(self, request):
        s = ForgotPasswordRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].strip().lower()
        user = CustomUser.objects.filter(email__iexact=email).first()
        ok_msg = {"detail": "Если аккаунт существует, код подтверждения отправлен на email."}
        if not user or not user.is_active:
            return Response(ok_msg)
        try:
            code = issue_password_reset_code(user)
            send_password_reset_email(email, code)
        except Exception:
            logger.exception("password reset email failed user_id=%s", user.pk)
            return Response(
                {"detail": "Не удалось отправить письмо. Попробуйте позже."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(ok_msg)


class ForgotPasswordVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Забыли пароль — проверить код из email",
        description=(
            "Check `email` and 6-digit `code` from the email. "
            "Returns `reset_token` — use it in POST /api/auth/password/forgot/reset/ with the new password."
        ),
        request=ForgotPasswordVerifySerializer,
        responses={
            200: inline_serializer(
                name="ForgotVerifyOk",
                fields={
                    "detail": serializers.CharField(),
                    "reset_token": serializers.CharField(),
                },
            )
        },
        examples=[OpenApiExample("Verify code", value={"email": "user@example.com", "code": "123456"})],
    )
    def post(self, request):
        s = ForgotPasswordVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].strip().lower()
        code = s.validated_data["code"]
        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user or not user.is_active:
            return Response({"detail": "Неверный или просроченный код."}, status=status.HTTP_400_BAD_REQUEST)
        prc = (
            PasswordResetCode.objects.filter(user=user, used=False, expires_at__gte=timezone.now())
            .order_by("-created_at")
            .first()
        )
        if not prc or not check_password(code, prc.code_hash):
            return Response({"detail": "Неверный или просроченный код."}, status=status.HTTP_400_BAD_REQUEST)
        prc.used = True
        prc.save(update_fields=["used"])
        reset_token = create_reset_session_token(user.pk)
        return Response(
            {
                "detail": "Код подтверждён. Отправьте reset_token и new_password на /api/auth/password/forgot/reset/.",
                "reset_token": reset_token,
            }
        )


class ForgotPasswordResetView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Забыли пароль — установить новый пароль",
        description="После проверки кода отправьте `reset_token` и `new_password`. Возвращает пару JWT токенов.",
        request=ForgotPasswordResetSerializer,
        responses={
            200: inline_serializer(
                name="ForgotResetOk",
                fields={
                    "detail": serializers.CharField(),
                    "user": UserMeSerializer(),
                    "tokens": inline_serializer(
                        name="TokenPairForgot",
                        fields={"access": serializers.CharField(), "refresh": serializers.CharField()},
                    ),
                },
            )
        },
        examples=[
            OpenApiExample(
                "Reset password",
                value={"reset_token": "<from verify step>", "new_password": "newsecret1"},
            )
        ],
    )
    def post(self, request):
        s = ForgotPasswordResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reset_token = s.validated_data["reset_token"].strip()
        new_password = s.validated_data["new_password"]
        try:
            uid = parse_reset_session_token(reset_token)
        except signing.BadSignature:
            return Response({"detail": "Неверный или просроченный reset_token."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = CustomUser.objects.get(pk=uid, is_active=True)
        except CustomUser.DoesNotExist:
            return Response({"detail": "Неверный или просроченный reset_token."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response(
            {
                "detail": "Пароль успешно изменён.",
                "user": UserMeSerializer(user).data,
                "tokens": _tokens_for_user(user),
            }
        )

