"""Katta fayllar: rasmiy Telegram Bot API botlarga 20 MB dan katta faylni yuklab olishga ruxsat bermaydi.

Ikki yo'l:
1. Lokal Bot API server (telegram-bot-api, 2000 MB gacha) — panelda «Bot API server» + «lokal rejim». Eng qulayi.
2. Lokal server bo'lmasa — bot bir martalik veb-yuklash havolasini beradi (/qrdrive/u/<token>, 24 soat).
   Fayl brauzerda yuklanadi, keyin odatdagi navbatdan o'tadi va QR Telegram'ga keladi.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .. import settings_store
from ..core.config import config
from ..core.crypto import token
from ..db.models import TgAccount, UploadTicket

TG_OFFICIAL_LIMIT = 20 * 1024 * 1024
TICKET_HOURS = 24


def bot_can_download(size: int | None, settings: dict[str, Any]) -> bool:
    """Lokal Bot API server ulangan bo'lsa — limit yo'q (max_file_mb ichida); rasmiy serverda — 20 MB."""
    if (settings.get("bot_api_url") or "").strip():
        return True
    return not size or size <= TG_OFFICIAL_LIMIT


async def create_ticket(session: AsyncSession, acc: TgAccount, chat_id: int, name: str, size: int | None,
                        caption: str = "") -> UploadTicket:
    ticket = UploadTicket(token=token(18), account_id=acc.id, chat_id=chat_id, name=name[:300], size=size, caption=caption,
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=TICKET_HOURS))
    session.add(ticket)
    await session.flush()
    return ticket


def ticket_url(settings: dict[str, Any], ticket: UploadTicket) -> str:
    return f"{settings_store.public_base(settings)}{config.prefix}/u/{ticket.token}"
