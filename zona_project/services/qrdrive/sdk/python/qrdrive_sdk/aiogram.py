"""Boshqa aiogram 3 botga QR Drive funksiyasini ulash:

    from qrdrive_sdk.aiogram import create_router

    dp.include_router(create_router(
        api_url="https://qr.firma.uz",
        api_key="qd_live_...",
        commands=["qr"],          # None — barcha fayllarga javob beradi
        reply_with_qr=True,
    ))
"""
from __future__ import annotations

import io
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from . import QRDriveClient, QRDriveError

FILE_FILTER = F.document | F.photo | F.video | F.audio | F.voice


def _file_of(msg: Message) -> tuple[Any, str] | None:
    if msg.document:
        return msg.document, msg.document.file_name or "fayl"
    if msg.photo:
        return msg.photo[-1], "rasm.jpg"
    if msg.video:
        return msg.video, msg.video.file_name or "video.mp4"
    if msg.audio:
        return msg.audio, msg.audio.file_name or "audio.mp3"
    if msg.voice:
        return msg.voice, "ovoz.ogg"
    return None


def create_router(api_url: str, api_key: str, *, commands: list[str] | None = None, reply_with_qr: bool = True,
                  use_telegram_id: bool = False, expire_days: int | None = None, name: str = "qrdrive") -> Router:
    """`commands` berilsa — faqat shu buyruq bilan (caption'da yoki faylga javob sifatida) ishlaydi.
    `use_telegram_id=True` — fayl QR Drive'dagi shu Telegram ID'li xodim papkasiga tushadi."""
    router = Router(name=name)
    client = QRDriveClient(api_url, api_key)

    async def process(msg: Message, source: Message, bot: Bot) -> None:
        found = _file_of(source)
        if not found:
            await msg.answer("Fayl topilmadi. Faylga javob sifatida yoki fayl bilan birga yuboring.")
            return
        obj, filename = found
        buf = io.BytesIO()
        await bot.download(obj, destination=buf)
        user = msg.from_user
        status = await msg.answer("⏳ Fayl saqlanmoqda…")
        try:
            res = await client.upload(buf.getvalue(), filename=filename, caption=source.caption or "", expire_days=expire_days,
                                      telegram_id=user.id if use_telegram_id and user else None,
                                      external_user="" if use_telegram_id else (user.username or str(user.id)) if user else "")
            if not res.ready and not res.failed:
                res = await client.wait_ready(res.id, timeout=120)
        except QRDriveError as e:
            await status.edit_text(f"❌ {e.detail}")
            return
        if res.failed:
            await status.edit_text(f"❌ {(res.error or {}).get('title', 'Fayl saqlanmadi')}")
            return
        if not res.ready:
            await status.edit_text("⏳ Fayl navbatda — tayyor bo'lgach havola keladi.")
            return
        await status.delete()
        if reply_with_qr and res.qr_png:
            await msg.answer_photo(BufferedInputFile(res.qr_png, "qr.png"), caption=f"✅ {res.url}")
        else:
            await msg.answer(f"✅ {res.url}")

    if commands:
        @router.message(Command(*commands))
        async def by_command(msg: Message, bot: Bot) -> None:
            await process(msg, msg.reply_to_message or msg, bot)

        @router.message(FILE_FILTER, F.caption.regexp(r"^/(" + "|".join(commands) + r")\b"))
        async def by_caption(msg: Message, bot: Bot) -> None:
            await process(msg, msg, bot)
    else:
        @router.message(FILE_FILTER)
        async def any_file(msg: Message, bot: Bot) -> None:
            await process(msg, msg, bot)

    return router
