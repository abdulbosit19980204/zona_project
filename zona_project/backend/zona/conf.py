"""Ilova sozlamalari. Xost loyihada settings.py ichida ZONA = {...} orqali o'zgartiriladi.

ZONA = {
    "COMPANY_NAME": "StarGroup",      # xaritaning markaziy tuguni
    "TITLE": "Responsibility Architecture",
    "FRONTEND_URL": "http://localhost:3000",  # Next.js interfeysi manzili (ma'lumot uchun)
    "PUBLIC_READ": False,              # True: tizimga kirmaganlar ham ko'radi (faqat o'qish)
    "ENCRYPTION_KEY": "",              # AI kalitlarini shifrlash kaliti (bo'sh: SECRET_KEY'dan)
    "CORS_ORIGINS": [],                # frontend boshqa domenda bo'lsa: ["https://zona.example.uz"]
    "AI_TIMEOUT": 60,                  # AI so'rovi uchun soniya
    "BOT_API_KEY": "",                 # Telegram bot kaliti (POST /api/bot/ask/, X-Bot-Key sarlavhasi)
}
Kirish tokenlari muddati settings.SIMPLE_JWT da (ACCESS_TOKEN_LIFETIME, REFRESH_TOKEN_LIFETIME).
Rollar: Django superuser = administrator; qolganlar Profile.role (admin / editor / viewer).
"""
import os

from django.conf import settings

DEFAULTS = {
    "COMPANY_NAME": "Tashkilot",
    "TITLE": "Responsibility Architecture",
    "FRONTEND_URL": "",
    "PUBLIC_READ": False,
    "ENCRYPTION_KEY": os.environ.get("ZONA_ENCRYPTION_KEY", ""),
    "CORS_ORIGINS": [],
    "AI_TIMEOUT": 60,
    "BOT_API_KEY": os.environ.get("ZONA_BOT_API_KEY", ""),  # Telegram bot uchun: X-Bot-Key sarlavhasi
}


def get(key):
    return getattr(settings, "ZONA", {}).get(key, DEFAULTS[key])
