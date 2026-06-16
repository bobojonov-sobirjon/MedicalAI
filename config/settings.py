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
    'apps.assistant',
    'apps.cabinet',
    'apps.medic',
    'apps.billing',
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
    "search_model": [],
    "topmenu_links": [
        {"name": "API Docs", "url": "/docs/", "new_window": True},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "order_with_respect_to": [
        # ——— 01. Аккаунты ———
        "accounts",
        "accounts.customuser",
        "accounts.familylink",
        # ——— 02. Справочники ———
        "catalog",
        "catalog.disease",
        "catalog.drug",
        "catalog.symptom",
        "catalog.bodypart",
        "catalog.drugviewlog",
        # ——— 03. История здоровья ———
        "history",
        "history.diseaserecord",
        "history.doctorvisit",
        "history.analysis",
        "history.prescription",
        # ——— 04. Помощник ———
        "assistant",
        "assistant.assistantdiagnosis",
        # ——— 05. Аптечка ———
        "cabinet",
        "cabinet.cabinetitem",
        # ——— 06. Сервисы (контент → уведомления → поддержка → логи) ———
        "medic",
        "medic.city",
        "medic.medicalfacility",
        "medic.usefultip",
        "medic.staticpage",
        "medic.faqitem",
        "medic.relaxasset",
        "medic.appupdatebroadcast",
        "medic.usertipsettings",
        "medic.diseasetipsubscription",
        "medic.notificationevent",
        "medic.feedbackticket",
        "medic.psychologyinquiry",
        "medic.chatthread",
        "medic.chatmessage",
        "medic.survey",
        "medic.surveyresponse",
        "medic.drugreview",
        "medic.druguserstarrating",
        "medic.drugdiscussionthread",
        "medic.discussionpost",
        "medic.druganalog",
        "medic.searchquerylog",
        "medic.auditlogentry",
        "medic.apierrorlog",
        # ——— 07. Оплата ———
        "billing",
        "billing.tariffplan",
        "billing.userbillingprofile",
        "billing.usersubscription",
        "billing.payment",
    ],
    "icons": {
        "accounts.customuser": "fas fa-users",
        "accounts.familylink": "fas fa-people-arrows",
        "catalog.disease": "fas fa-virus",
        "catalog.drug": "fas fa-pills",
        "catalog.symptom": "fas fa-head-side-cough",
        "catalog.bodypart": "fas fa-child",
        "catalog.drugviewlog": "fas fa-eye",
        "history.diseaserecord": "fas fa-notes-medical",
        "history.doctorvisit": "fas fa-user-md",
        "history.analysis": "fas fa-vial",
        "history.prescription": "fas fa-file-prescription",
        "assistant.assistantdiagnosis": "fas fa-robot",
        "cabinet.cabinetitem": "fas fa-briefcase-medical",
        "medic.city": "fas fa-city",
        "medic.medicalfacility": "fas fa-hospital",
        "medic.usefultip": "fas fa-lightbulb",
        "medic.staticpage": "fas fa-file-alt",
        "medic.faqitem": "fas fa-question-circle",
        "medic.relaxasset": "fas fa-spa",
        "medic.notificationevent": "fas fa-bell",
        "medic.feedbackticket": "fas fa-comment-dots",
        "medic.psychologyinquiry": "fas fa-brain",
        "medic.chatthread": "fas fa-comments",
        "medic.chatmessage": "fas fa-comment",
        "medic.drugreview": "fas fa-star-half-alt",
        "medic.druganalog": "fas fa-exchange-alt",
        "medic.auditlogentry": "fas fa-clipboard-list",
        "medic.apierrorlog": "fas fa-exclamation-triangle",
        "medic.searchquerylog": "fas fa-search",
        "billing.tariffplan": "fas fa-tags",
        "billing.usersubscription": "fas fa-id-card",
        "billing.payment": "fas fa-credit-card",
        "billing.userbillingprofile": "fas fa-wallet",
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
# По умолчанию используем папку media рядом с проектом (удобно для локальной
# разработки на Windows/macOS/Linux). В проде MEDIA_ROOT задаётся через env,
# например MEDIA_ROOT=/var/www/media (см. systemd unit / docker compose).
MEDIA_ROOT = os.getenv('MEDIA_ROOT', os.path.join(BASE_DIR, 'media'))

# Публичный базовый URL приложения. Используется, например, для построения
# абсолютных ссылок на загруженные файлы (image_url у учреждений и т.п.),
# когда Django стоит за reverse proxy и request.build_absolute_uri может
# вернуть неверный хост/схему. Пример: https://api.medicalai.com
PUBLIC_BASE_URL = (os.getenv('PUBLIC_BASE_URL', '') or '').rstrip('/')
# OCR (RuTronix) часто >30 с: без gunicorn.conf.py Gunicorn убивает воркер (WORKER TIMEOUT). См. gunicorn.conf.py и deploy/medical.service.example.


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
        {'name': 'Профиль', 'description': 'Текущий пользователь: чтение и обновление своего ЛК (ТЗ §7.7) — GET/PATCH /api/auth/me/.'},
        {
            'name': 'Профили',
            'description': (
                'Несколько медицинских профилей в одном аккаунте (ТЗ §7.7): карусель, добавить, '
                'редактировать, удалить. GET|POST /api/me/profiles/, GET|PUT|PATCH|DELETE /api/me/profiles/{id}/. '
                'Свой ЛК — GET|PATCH /api/auth/me/.'
            ),
        },
        {'name': 'Опросы', 'description': 'Всплывающие опросы из админки: список и отправка ответа (ТЗ §8.2.3).'},
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
        {'name': 'Контент', 'description': 'Статические страницы (о компании, конфиденциальность), конфиг приложения.'},
        {'name': 'Медучреждения', 'description': 'Города, аптеки и больницы, карточка учреждения (ТЗ §7.13).'},
        {'name': 'Уведомления', 'description': 'События (REST), полезная лента, настройки; WebSocket ws/notifications/?token=JWT для push в реальном времени (ТЗ §7.12).'},
        {'name': 'Поддержка', 'description': 'Обратная связь, вопрос психологу, чат со службой поддержки (ТЗ §7.17–7.18).'},
        {'name': 'Релакс', 'description': 'Лента GIF, видео и музыки для психоэмоциональной разгрузки (ТЗ §7.21, §5.9).'},
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

# RuTronix (единый API для ИИ-моделей)
RUTRONIX_API_KEY = os.getenv('RUTRONIX_API_KEY', '').strip()
RUTRONIX_MODEL = os.getenv('RUTRONIX_MODEL', 'one-perfect-answer').strip()
# Surat/OCR: alohida model (one-perfect-answer faqat matn — vision emas).
# RuTronix kabinetidagi vision-qo‘llab-quvvatlaydigan model slug (masalan gpt-4o-mini).
RUTRONIX_VISION_MODEL = os.getenv('RUTRONIX_VISION_MODEL', 'gpt-4o-mini').strip()
RUTRONIX_BASE_URL = os.getenv('RUTRONIX_BASE_URL', 'https://api.rutronix.ai').strip()
# False = faqat RuTronix; Gemini zaxira o‘chirilgan (production uchun tavsiya).
USE_GEMINI_FALLBACK = os.getenv('USE_GEMINI_FALLBACK', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
# httpx: text chat (uniform timeout, seconds)
RUTRONIX_CHAT_TIMEOUT_S = float(os.getenv('RUTRONIX_CHAT_TIMEOUT_S', '45'))
# Vision/OCR: split timeouts (httpx read = time to first byte + streaming body from RuTronix).
# Default read 90s — OCR often needs 25–60s; cap read below Gunicorn --timeout (e.g. 120).
RUTRONIX_VISION_WRITE_S = float(os.getenv('RUTRONIX_VISION_WRITE_S', '120'))
RUTRONIX_VISION_CONNECT_S = float(os.getenv('RUTRONIX_VISION_CONNECT_S', '12'))
RUTRONIX_VISION_TIMEOUT_S = float(os.getenv('RUTRONIX_VISION_TIMEOUT_S', '90'))
if 'RUTRONIX_VISION_READ_S' in os.environ:
    RUTRONIX_VISION_READ_S = float(os.getenv('RUTRONIX_VISION_READ_S', '90'))
else:
    # Legacy single knob: read follows RUTRONIX_VISION_TIMEOUT_S (no artificial 22s cap).
    RUTRONIX_VISION_READ_S = RUTRONIX_VISION_TIMEOUT_S
# Before RuTronix vision: resize + JPEG (see apps/core/rutronix.py). OCR still needs Gunicorn --timeout >= 60–120 on slow providers.
RUTRONIX_VISION_MAX_IMAGE_SIDE = int(os.getenv('RUTRONIX_VISION_MAX_IMAGE_SIDE', '1280'))
RUTRONIX_VISION_JPEG_QUALITY = int(os.getenv('RUTRONIX_VISION_JPEG_QUALITY', '82'))

PSYCHOLOGY_EMAIL = os.getenv('PSYCHOLOGY_EMAIL', 'psychology@medic-ai.ru').strip()
FREE_TRIAL_MONTHS = int(os.getenv('FREE_TRIAL_MONTHS', '3'))
SUBSCRIPTION_EXPIRY_WARNING_DAYS = os.getenv('SUBSCRIPTION_EXPIRY_WARNING_DAYS', '7,3,1')
ENABLE_SUBSCRIPTION_SCHEDULER = os.getenv('ENABLE_SUBSCRIPTION_SCHEDULER', 'true').strip()

# Robokassa (ТЗ §4.2)
ROBOKASSA_MERCHANT_LOGIN = os.getenv('ROBOKASSA_MERCHANT_LOGIN', 'MedicAi').strip()
ROBOKASSA_PASSWORD1 = os.getenv('ROBOKASSA_PASSWORD1', '').strip()
ROBOKASSA_PASSWORD2 = os.getenv('ROBOKASSA_PASSWORD2', '').strip()
ROBOKASSA_TEST_MODE = os.getenv('ROBOKASSA_TEST_MODE', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
ROBOKASSA_PAYMENT_URL = os.getenv(
    'ROBOKASSA_PAYMENT_URL',
    'https://auth.robokassa.ru/Merchant/Index.aspx',
).strip()
ROBOKASSA_SUCCESS_URL = os.getenv('ROBOKASSA_SUCCESS_URL', '').strip()
ROBOKASSA_FAIL_URL = os.getenv('ROBOKASSA_FAIL_URL', '').strip()
ROBOKASSA_APPEND_REDIRECT_URLS = os.getenv('ROBOKASSA_APPEND_REDIRECT_URLS', 'false').strip().lower() in (
    '1', 'true', 'yes', 'on',
)

# In-process scheduler for reminder notifications (dev / single instance)
ENABLE_REMINDER_SCHEDULER = os.getenv('ENABLE_REMINDER_SCHEDULER', 'true').strip()

# TZ §3.3 optional global API key for mobile (header X-Backend-Key)
BACKEND_API_KEY = os.getenv('BACKEND_API_KEY', '').strip()
REQUIRE_BACKEND_API_KEY = os.getenv('REQUIRE_BACKEND_API_KEY', 'false').strip().lower() in ('1', 'true', 'yes')