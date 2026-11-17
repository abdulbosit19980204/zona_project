"""API bog'liqliklari: panel foydalanuvchisi (Zona SSO) va tashqi API kalitlari (scope, IP, rate limit)."""
from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import API_KEY_PREFIX, hash_api_key
from ..core.security import AuthError, Principal, verify_sso
from ..db.models import ApiKey
from ..db.session import get_session

SCOPES = {
    "files:write": "Fayl yuklash, havolani yangilash/bekor qilish",
    "files:read": "Fayllar ro'yxati va ma'lumotlari, QR olish",
    "qr:generate": "Istalgan havoladan QR yasash",
    "employees:read": "Xodimlar ro'yxati",
}


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tizimga kiring")
    return header[7:].strip()


def principal(request: Request) -> Principal:
    try:
        return verify_sso(_bearer(request))
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e


def require(role: str):
    def dep(user: Principal = Depends(principal)) -> Principal:
        if not user.can(role):
            names = {"admin": "Admin", "superadmin": "Superadmin"}
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Bu amal uchun «{names.get(role, role)}» huquqi kerak")
        return user
    return dep


viewer = require("viewer")
admin = require("admin")
superadmin = require("superadmin")


# --- tashqi API ---
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_ok(key: ApiKey) -> bool:
    limit = key.rate_limit or 0
    if limit <= 0:
        return True
    window, now = _hits[key.key_hash], time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


def _ip_ok(key: ApiKey, ip: str) -> bool:
    if not key.allowed_ips:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for item in key.allowed_ips:
        try:
            if addr in ipaddress.ip_network(str(item), strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


def api_key(scope: str):
    async def dep(request: Request, session: AsyncSession = Depends(get_session)) -> ApiKey:
        raw = _bearer(request)
        if not raw.startswith(API_KEY_PREFIX):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API kaliti noto'g'ri")
        key = (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if key is None or key.revoked or (key.expires_at and key.expires_at < now):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API kaliti noto'g'ri, bekor qilingan yoki muddati tugagan")
        request.state.api_key_id = key.id
        if not _ip_ok(key, client_ip(request)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu IP manzildan ruxsat yo'q")
        if scope not in (key.scopes or []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Kalitda «{scope}» ruxsati yo'q")
        if not _rate_ok(key):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "So'rovlar soni chegaradan oshdi, bir daqiqadan keyin urinib ko'ring")
        key.last_used_at, key.uses = now, (key.uses or 0) + 1
        await session.commit()
        return key
    return dep
