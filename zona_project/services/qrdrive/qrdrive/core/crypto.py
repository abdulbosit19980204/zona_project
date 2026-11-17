"""Maxfiy qiymatlarni shifrlash (Fernet, MASTER_KEY'dan), API kalit va havola paroli xeshlari."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken

from .config import config

_ph = PasswordHasher()


def _fernet(key: str | None = None) -> Fernet:
    digest = hashlib.sha256((key or config.master_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""  # kalit almashgan — qiymatni qayta kiritish kerak


def encrypt_json(data: dict[str, Any]) -> str:
    return encrypt(json.dumps(data, ensure_ascii=False))


def decrypt_json(token: str) -> dict[str, Any]:
    raw = decrypt(token)
    return json.loads(raw) if raw else {}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


API_KEY_PREFIX = "qd_live_"


def new_api_key() -> tuple[str, str, str]:
    """(to'liq kalit — faqat bir marta ko'rsatiladi, ko'rinadigan prefiks, xesh)."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[: len(API_KEY_PREFIX) + 6], hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    # Kalit 256 bit tasodifiy — sekin xesh shart emas; HMAC bilan bazadagi xesh MASTER_KEY'ga bog'lanadi
    return hmac.new(config.master_key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def token(nbytes: int = 24) -> str:
    """Taxmin qilib bo'lmaydigan token (>= 128 bit)."""
    return secrets.token_urlsafe(nbytes)


def sign_webhook(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
