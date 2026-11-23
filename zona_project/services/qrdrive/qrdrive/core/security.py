"""Panel foydalanuvchilari: Zona platformasi JWT'si (SSO). Token shu yerda, tarmoqqa chiqmasdan tekshiriladi —
Zona backendi vaqtincha ishlamasa ham, amaldagi seanslar QR Drive bilan ishlashda davom etadi."""
from __future__ import annotations

from dataclasses import dataclass

import jwt

from .config import config

ROLES = ("viewer", "admin", "superadmin")
RANK = {r: i for i, r in enumerate(ROLES)}
# Zona roli -> QR Drive roli
ZONA_ROLE_MAP = {"admin": "superadmin", "editor": "admin", "viewer": "viewer"}


@dataclass
class Principal:
    username: str
    name: str
    role: str
    user_id: int | None = None

    def can(self, role: str) -> bool:
        return RANK[self.role] >= RANK[role]


class AuthError(Exception):
    pass


def verify_sso(token: str) -> Principal:
    try:
        claims = jwt.decode(token, config.sso_secret, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.ExpiredSignatureError as e:
        raise AuthError("Seans muddati tugagan") from e
    except jwt.PyJWTError as e:
        raise AuthError("Token yaroqsiz") from e
    if claims.get("token_type") != "access":
        raise AuthError("Token yaroqsiz")
    username = str(claims.get("username") or f"user-{claims.get('user_id')}")
    if str(claims.get("zrole") or "") == "inventory":  # faqat IT inventarizatsiya logini — QR Drive yopiq
        raise AuthError("Bu foydalanuvchiga QR Drive ruxsati yo'q")
    role = ZONA_ROLE_MAP.get(str(claims.get("zrole") or "viewer"), "viewer")
    return Principal(username=username, name=str(claims.get("name") or username), role=role, user_id=claims.get("user_id"))
