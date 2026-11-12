"""Backend sozlamalari: Django + DRF + JWT + WebSocket (Channels) + SQLite.
Interfeys — alohida Next.js ilova (../frontend), API ga /api/ orqali murojaat qiladi."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "daphne",  # runserver ni ASGI (HTTP + WebSocket) rejimida ishga tushiradi; birinchi turishi shart
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "channels",
    "zona",
]

ZONA = {
    "COMPANY_NAME": "StarGroup",
    "FRONTEND_URL": os.environ.get("ZONA_FRONTEND_URL", "http://localhost:3000"),
    "PUBLIC_READ": os.environ.get("ZONA_PUBLIC_READ") == "1",
    # Frontend API ga to'g'ridan-to'g'ri (proksisiz) murojaat qilsa, uning manzili:
    "CORS_ORIGINS": [o for o in os.environ.get("ZONA_CORS_ORIGINS", "http://localhost:3000").split(",") if o],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
}

MIDDLEWARE = [
    "zona.middleware.ZonaCorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Bitta jarayon uchun xotirada. Bir nechta server jarayoni bo'lsa Redis: channels_redis.core.RedisChannelLayer
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": os.environ.get("ZONA_DB_PATH", BASE_DIR / "db.sqlite3"),
}}

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
