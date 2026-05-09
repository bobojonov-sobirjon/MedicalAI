import os
from datetime import timedelta
from pathlib import Path


# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    load_dotenv = None
    
    
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-he%+_lkl7^mfq%25y(#2=j7o%@2xzpb$o8=aj8_e428uowd9)$'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition

LOCAL_APPS = [
    'apps.accounts',
    'apps.catalog',
    'apps.history',
    'apps.cabinet',
    'apps.assistant',
    'apps.medic',
]

INSTALLED_APPS = [
    'daphne',
    'channels',
    'jazzmin',
    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    'django_filters',
    *LOCAL_APPS,
]

JAZZMIN_SETTINGS = {
    "site_title": "MedicalAI Admin",
    "site_header": "MedicalAI",
    "site_brand": "MedicalAI",
    "welcome_sign": "Welcome to MedicalAI Admin",
    "copyright": "MedicalAI",
    "search_model": [
        "accounts.CustomUser",
        "catalog.Disease",
        "catalog.Drug",
        "catalog.DrugViewLog",
        "history.DiseaseRecord",
        "cabinet.CabinetItem",
    ],
    "topmenu_links": [
        {"name": "API Docs", "url": "/docs/", "new_window": True},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "order_with_respect_to": ["accounts", "catalog", "history", "cabinet", "assistant", "medic"],
    "icons": {
        "accounts.customuser": "fas fa-user",
        "accounts.socialaccount": "fas fa-link",
        "accounts.passwordresetcode": "fas fa-envelope",
        "catalog.disease": "fas fa-virus",
        "catalog.drug": "fas fa-pills",
        "history.diseaserecord": "fas fa-notes-medical",
        "catalog.drugviewlog": "fas fa-eye",
        "cabinet.cabinetitem": "fas fa-briefcase-medical",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
}

LOCAL_MIDDLEWARE = [
    'config.middleware.middleware.JsonErrorResponseMiddleware',
    'config.middleware.middleware.Custom404Middleware',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'config.middleware.apikey_middleware.BackendApiKeyMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    *LOCAL_MIDDLEWARE,
]

ROOT_URLCONF = 'config.urls'

# WebSocket (Channels): уведомления в реальном времени — см. /ws/notifications/
ASGI_APPLICATION = 'config.asgi.application'
# Для нескольких воркеров укажите Redis и пакет channels-redis, затем задайте CHANNEL_LAYERS вручную.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'medical_ai'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', '0576'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = "/media/"
# Production uchun /var/www/media, development uchun local media folder
MEDIA_ROOT = os.getenv('MEDIA_ROOT', '/var/www/media')


LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FileUploadParser",
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    "PAGE_SIZE": 100,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:5173"
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:5173"
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRFToken']

# CORS Headers
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'cache-control',
    'pragma',
]

# CORS Methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# CSRF Settings for production
CSRF_COOKIE_SECURE = False  # Set True if using HTTPS
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_USE_SESSIONS = False
CSRF_COOKIE_NAME = 'csrftoken'

# Session Settings
SESSION_COOKIE_SECURE = False  # Set True if using HTTPS
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True

# Security Settings for development/production
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)

AUTH_USER_MODEL = 'accounts.CustomUser'

SITE_ID = 1


EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true').strip().lower() in ('1', 'true', 'yes', 'y')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '').strip()
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '').strip()

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', '').strip() or (
    'django.core.mail.backends.smtp.EmailBackend'
    if (EMAIL_HOST_USER and EMAIL_HOST_PASSWORD)
    else 'django.core.mail.backends.console.EmailBackend'
)

DEFAULT_FROM_EMAIL = (
    os.getenv('DEFAULT_FROM_EMAIL', '').strip()
    or EMAIL_HOST_USER
    or 'no-reply@medicalai.local'
)


# DRF Spectacular Configuration
SPECTACULAR_SETTINGS = {
    'TITLE': 'MedicAI API',
    'DESCRIPTION': (
        'Бэкенд MedicAI: REST API с JWT, справочники, история болезней, помощник (ИИ), '
        'уведомления, медучреждения, аптечка и др. по ТЗ.'
    ),
    'VERSION': 'v1',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
    },
    'SWAGGER_UI_FAVICON_HREF': '/static/favicon.ico',
    'REDOC_UI_SETTINGS': {
        'hideDownloadButton': True,
        'hideHostname': True,
    },
    'TAGS': [
        {'name': 'Авторизация', 'description': 'Регистрация, вход, обновление токена, соцсети, смена и восстановление пароля.'},
        {'name': 'Профиль', 'description': 'Текущий пользователь: чтение и обновление профиля (ЛК).'},
        {'name': 'Заболевания', 'description': 'Публичный справочник заболеваний, поиск, карточка с рекомендуемыми лекарствами.'},
        {'name': 'Лекарства', 'description': 'Публичный справочник: список и карточка лекарства (без отзывов и соц. функций).'},
        {'name': 'Отзывы на лекарства', 'description': 'Одобренные отзывы и отправка отзыва на модерацию по лекарству.'},
        {'name': 'Обсуждения лекарств', 'description': 'Тред обсуждения лекарства: список сообщений и отправка сообщения.'},
        {'name': 'Оценки лекарств', 'description': 'Оценка лекарства звёздами (не чаще одного изменения за 24 часа).'},
        {'name': 'Аналоги лекарств', 'description': 'Список аналогов по лекарству (данные из БД; наполнение парсером/админкой).'},
        {'name': 'Просмотры лекарств', 'description': 'Учёт открытия карточки лекарства для списка «ранее просмотренные».'},
        {'name': 'История здоровья', 'description': 'Личные записи о болезнях пользователя (ТЗ §7.8).'},
        {'name': 'Визиты врача', 'description': 'Посещения врача внутри записи истории болезни.'},
        {'name': 'Анализы', 'description': 'Анализы внутри записи истории; загрузка фото, OCR (ТЗ).'},
        {'name': 'Рецепты', 'description': 'Фото рецептов внутри записи истории болезни.'},
        {'name': 'Помощник', 'description': 'Симптомы и ИИ-подбор (Gemini), справочник симптомов/частей тела, FAQ.'},
        {'name': 'Аптечка', 'description': 'Моя аптечка: список, добавление, распознавание по фото.'},
        {'name': 'Контент', 'description': 'Статические страницы (о компании, конфиденциальность), конфиг приложения, опросы.'},
        {'name': 'Медучреждения', 'description': 'Города, аптеки и больницы, карточка учреждения (ТЗ §7.13).'},
        {'name': 'Уведомления', 'description': 'События (REST), полезная лента, настройки; WebSocket ws/notifications/?token=JWT для push в реальном времени (ТЗ §7.12).'},
        {'name': 'Поддержка', 'description': 'Обратная связь, вопрос психологу, чат со службой поддержки (ТЗ §7.17–7.18).'},
        {'name': 'Релакс', 'description': 'Лента GIF и видео (ТЗ §7.21).'},
        {'name': 'Голос', 'description': 'Распознавание речи для полей форм (заглушка / интеграция STT, ТЗ §8.2.2).'},
        {'name': 'Администрирование', 'description': 'Метрики и сводки для персонала (ТЗ §5.1).'},
    ],
    'PREPROCESSING_HOOKS': [],
    'POSTPROCESSING_HOOKS': [],
    'GENERIC_ADDITIONAL_PROPERTIES': None,
    'CAMPAIGN': None,
    'CONTACT': {
        'name': 'Поддержка API MedicAI',
        'email': 'support@medic-ai.ru',
    },
    'LICENSE': {
        'name': 'Проприетарная лицензия',
    },
}

# TZ §7.5 forgot password — email code TTL and signed reset_token TTL (step after verify)
PASSWORD_RESET_CODE_TTL_MINUTES = int(os.getenv('PASSWORD_RESET_CODE_TTL_MINUTES', '15'))
PASSWORD_RESET_SESSION_TTL_MINUTES = int(os.getenv('PASSWORD_RESET_SESSION_TTL_MINUTES', '15'))

# Google Gemini (Stage 2: assistant + OCR)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash').strip()

# RuTronix (единый API для ИИ-моделей; замена для Gemini в текстовых задачах)
RUTRONIX_API_KEY = os.getenv('RUTRONIX_API_KEY', '').strip()
RUTRONIX_MODEL = os.getenv('RUTRONIX_MODEL', 'one-perfect-answer').strip()
RUTRONIX_BASE_URL = os.getenv('RUTRONIX_BASE_URL', 'https://api.rutronix.ai').strip()

PSYCHOLOGY_EMAIL = os.getenv('PSYCHOLOGY_EMAIL', 'psychology@medic-ai.ru').strip()
FREE_TRIAL_MONTHS = int(os.getenv('FREE_TRIAL_MONTHS', '3'))

# In-process scheduler for reminder notifications (dev / single instance)
ENABLE_REMINDER_SCHEDULER = os.getenv('ENABLE_REMINDER_SCHEDULER', 'true').strip()

# TZ §3.3 optional global API key for mobile (header X-Backend-Key)
BACKEND_API_KEY = os.getenv('BACKEND_API_KEY', '').strip()
REQUIRE_BACKEND_API_KEY = os.getenv('REQUIRE_BACKEND_API_KEY', 'false').strip().lower() in ('1', 'true', 'yes')