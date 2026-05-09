from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema
from apps.accounts.models import CustomUser
@method_decorator(csrf_exempt, name='dispatch')
class SwaggerTokenView(APIView):
    """
    Точка выдачи токена для Swagger (OAuth2 password): вход по email, без проверки пароля.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Получить токен (для Swagger UI)",
        description=(
            "Совместимость с OAuth2 password flow в Swagger: передайте grant_type=password и username=email. "
            "Поле password игнорируется; при отсутствии пользователя с таким email он будет создан."
        ),
        request={
            "application/x-www-form-urlencoded": {
                "type": "object",
                "properties": {
                    "grant_type": {"type": "string", "example": "password", "description": "Должно быть password"},
                    "username": {
                        "type": "string",
                        "format": "email",
                        "example": "user@example.com",
                        "description": "Email пользователя",
                    },
                    "password": {
                        "type": "string",
                        "example": "password",
                        "description": "Не используется (оставлено для совместимости с формой OAuth2)",
                    },
                },
                "required": ["grant_type", "username"],
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string", "description": "JWT доступа"},
                    "refresh_token": {"type": "string", "description": "JWT обновления"},
                    "token_type": {"type": "string", "example": "Bearer"},
                    "expires_in": {"type": "integer", "example": 604800, "description": "Срок жизни access_token в секундах"},
                    "scope": {"type": "string", "example": "read write"},
                },
            },
            400: {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "error_description": {"type": "string"},
                },
            },
        },
        tags=["Авторизация"],
    )
    def post(self, request):
        """Выдача JWT для авторизации запросов из Swagger."""
        username = request.data.get('username')  # This will be the email
        password = request.data.get('password', '')  # Not used, but kept for compatibility
        grant_type = request.data.get('grant_type', 'password')
        
        if grant_type != 'password':
            return JsonResponse({
                'error': 'unsupported_grant_type',
                'error_description': 'Only password grant type is supported'
            }, status=400)
        
        if not username:
            return JsonResponse({
                'error': 'invalid_request',
                'error_description': 'Email is required'
            }, status=400)
        
        # Try to find user by email
        try:
            user = CustomUser.objects.get(email=username)
        except CustomUser.DoesNotExist:
            # If user doesn't exist, create a new one (similar to your login flow)
            user = CustomUser.objects.create_user(
                username=username,  # Use email as username
                email=username,
                phone_number='',  # Will be set later if needed
                first_name='',
                last_name=''
            )
        
        # Generate tokens directly (no password check needed)
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        return JsonResponse({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': 604800,  # 7 days in seconds
            'scope': 'read write'
        })