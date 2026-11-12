"""AI kalitlarini bazada shifrlab saqlash (Fernet: AES-128-CBC + HMAC)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from . import conf


def _fernet():
    secret = conf.get("ENCRYPTION_KEY") or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(("zona-ai:" + secret).encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # SECRET_KEY yoki ENCRYPTION_KEY o'zgargan: kalitni qayta kiritish kerak
        return ""


def mask(value: str) -> str:
    if not value:
        return ""
    return "••••" + value[-4:] if len(value) > 8 else "••••"
