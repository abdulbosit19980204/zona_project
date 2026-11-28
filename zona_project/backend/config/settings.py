"""Backend sozlamalari: Django + DRF + JWT + WebSocket (Channels) + SQLite.
Interfeys — alohida Next.js ilova (../frontend), API ga /api/ orqali murojaat qiladi."""
import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise ImproperlyConfigured("Ishlab chiqarishda DJANGO_SECRET_KEY ni o'rnating (deploy/env.example ga qarang).")
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
    "support",  # Telegram support bot (alohida jadvallar: support_*)
    "inventory",  # IT inventarizatsiya (alohida jadvallar: inventory_*)
    "prbc",  # PRBC integratsiyasi: xodimlar sinxronlashi, vazifalar API orqali (alohida jadvallar: prbc_*)
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
    # Mikroservislar (QR Drive) access tokenni shu kalit bilan o'zi tekshiradi — Zona'ga so'rov yubormasdan
    "SIGNING_KEY": os.environ.get("ZONA_JWT_SECRET") or SECRET_KEY,
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

# WebSocket kanal qatlami va kesh. ZONA_REDIS_URL bo'lsa (masalan unix:///run/foydali-redis/redis.sock) — Redis:
# bir nechta backend worker'i (ZONA_WEB_WORKERS) va bot/PRBC jarayonlari xabar va keshni bo'lishadi.
# Bo'lmasa (lokal, testlar) — jarayon xotirasida, bitta worker.
REDIS_URL = "" if "test" in sys.argv[1:2] else os.environ.get("ZONA_REDIS_URL", "").strip()


def _redis_db(n):
    return f"{REDIS_URL}{'&' if '?' in REDIS_URL else '?'}db={n}"


if REDIS_URL:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {
        # socket_timeout > kutish (BZPOPMIN 5 s): redis-py 8 da standart 5 s — bir xil bo'lsa WebSocket har 5 s da
        # «Timeout reading» bilan uziladi
        "hosts": [{"address": _redis_db(0), "socket_timeout": 30, "socket_connect_timeout": 2}], "prefix": "foydali",
        "group_expiry": 7 * 86400,  # guruh a'zoligi ping'da yangilanadi (realtime.py); bu — yiqilgan ulanishlar uchun
    }}}
    CACHES = {"default": {"BACKEND": "zona.cache.SafeRedisCache", "LOCATION": _redis_db(1), "KEY_PREFIX": "foydali",
                          "OPTIONS": {"socket_timeout": 2, "socket_connect_timeout": 1}}}
else:
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
    # WAL: o'qish va yozish bir-birini to'smaydi; IMMEDIATE: parallel yozishda "database is locked" bo'lmaydi
    "OPTIONS": {"init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                "transaction_mode": "IMMEDIATE", "timeout": 20},
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

# Ishlab chiqarish: nginx ortida HTTPS
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    _secure = os.environ.get("DJANGO_SECURE_COOKIES", "1") == "1"  # HTTPS bo'lmasa (faqat IP orqali) — 0
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = _secure
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

# Jurnal: systemd/journald orqali ko'rinadi (journalctl -u zona-backend)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {"django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
