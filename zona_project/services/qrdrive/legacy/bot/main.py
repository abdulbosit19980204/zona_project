"""Kadrlar bo'limi uchun bot: fayl -> Synology -> ommaviy havola -> QR kod."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import tempfile
from datetime import datetime

import qrcode
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message, User

from synology import Synology, SynologyError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kadrlar-bot")


def env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None or val == "":
        if default is None:
            raise SystemExit(f".env da {name} ko'rsatilmagan")
    return val or ""


BOT_TOKEN = env("BOT_TOKEN")
TELEGRAM_API_URL = os.getenv("TELEGRAM_API_URL", "").strip()  # bo'sh bo'lsa - oddiy Telegram API (20 MB)
MAX_FILE_MB = int(env("MAX_FILE_MB", "100"))
BASE_FOLDER = "/" + env("SYNO_BASE_FOLDER", "/Kadrlar").strip("/")
SHARE_EXPIRE_DAYS = int(env("SHARE_EXPIRE_DAYS", "0"))
SHARE_PASSWORD = os.getenv("SHARE_PASSWORD", "")
ALLOWED_IDS = {int(x) for x in re.split(r"[,\s]+", os.getenv("ALLOWED_USER_IDS", "")) if x.strip()}

syno = Synology(
    base_url=env("SYNO_URL"),
    user=env("SYNO_USER"),
    password=env("SYNO_PASS"),
    verify_ssl=env("SYNO_VERIFY_SSL", "true").lower() in ("1", "true", "yes"),
)

if TELEGRAM_API_URL:
    session = AiohttpSession(api=TelegramAPIServer.from_base(TELEGRAM_API_URL, is_local=True))
    bot = Bot(BOT_TOKEN, session=session)
else:
    bot = Bot(BOT_TOKEN)
dp = Dispatcher()

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_name(name: str, limit: int = 150) -> str:
    name = _BAD_CHARS.sub("_", name).strip(" .")
    return (name or "fayl")[:limit]


def folder_for(user: User) -> str:
    if user.username:
        return safe_name(user.username, 64)
    return safe_name(f"{user.first_name or 'user'}_{user.id}", 64)


def make_qr(url: str) -> bytes:
    img = qrcode.make(url, box_size=10, border=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def extract_file(msg: Message) -> tuple[str, int | None, str] | None:
    ts = datetime.now().strftime("%H%M%S")
    if msg.document:
        d = msg.document
        return d.file_id, d.file_size, d.file_name or f"fayl_{ts}"
    if msg.photo:
        p = msg.photo[-1]  # eng katta o'lcham
        return p.file_id, p.file_size, f"rasm_{ts}.jpg"
    if msg.video:
        v = msg.video
        return v.file_id, v.file_size, v.file_name or f"video_{ts}.mp4"
    if msg.audio:
        a = msg.audio
        return a.file_id, a.file_size, a.file_name or f"audio_{ts}.mp3"
    return None


@dp.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    await msg.answer(
        "Assalomu alaykum! Menga fayl yuboring (hujjat, rasm, video) — "
        f"uni serverga saqlab, havolasini QR kod ko'rinishida qaytaraman.\n"
        f"Maksimal hajm: {MAX_FILE_MB} MB.\n\n"
        "Rasmni sifati buzilmasligi uchun «Fayl sifatida» yuboring."
    )


@dp.message(Command("id"))
async def cmd_id(msg: Message) -> None:
    await msg.answer(f"Sizning Telegram ID: <code>{msg.from_user.id}</code>", parse_mode="HTML")


@dp.message(F.document | F.photo | F.video | F.audio)
async def handle_file(msg: Message) -> None:
    user = msg.from_user
    if user.id not in ALLOWED_IDS:
        log.warning("Ruxsatsiz urinish: %s (@%s)", user.id, user.username)
        await msg.answer(
            f"Sizga ruxsat berilmagan. ID'ingiz: <code>{user.id}</code> — uni administratorga yuboring.",
            parse_mode="HTML",
        )
        return

    file_id, size, orig_name = extract_file(msg)
    if size and size > MAX_FILE_MB * 1024 * 1024:
        await msg.answer(f"Fayl juda katta ({size / 1024 / 1024:.1f} MB). Ruxsat: {MAX_FILE_MB} MB gacha.")
        return

    status = await msg.answer("⏳ Fayl qabul qilinmoqda...")
    local_path: str | None = None
    try:
        try:
            tg_file = await bot.get_file(file_id)
        except TelegramBadRequest as e:
            if "too big" in str(e).lower():
                await status.edit_text("Fayl juda katta: Telegram uni berishga ruxsat bermadi.")
                return
            raise

        if TELEGRAM_API_URL and os.path.isabs(tg_file.file_path) and os.path.exists(tg_file.file_path):
            local_path = tg_file.file_path  # lokal Bot API server faylni umumiy volume'ga yozgan
        else:
            fd, local_path = tempfile.mkstemp(prefix="kb_")
            os.close(fd)
            await bot.download_file(tg_file.file_path, destination=local_path)

        filename = f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{safe_name(orig_name)}"
        folder = f"{BASE_FOLDER}/{folder_for(user)}"

        await status.edit_text("⏳ Serverga yuklanmoqda...")
        remote_path = await syno.upload(local_path, folder, filename)

        await status.edit_text("⏳ Havola yaratilmoqda...")
        url = await syno.share(remote_path, SHARE_EXPIRE_DAYS, SHARE_PASSWORD)

        caption = f"✅ Saqlandi: <code>{remote_path}</code>\n🔗 {url}"
        if SHARE_EXPIRE_DAYS > 0:
            caption += f"\n⏰ Havola {SHARE_EXPIRE_DAYS} kun amal qiladi"
        await msg.answer_photo(BufferedInputFile(make_qr(url), filename="qr.png"), caption=caption, parse_mode="HTML")
        await status.delete()
        log.info("OK: %s (@%s) -> %s", user.id, user.username, remote_path)
    except SynologyError as e:
        log.exception("Synology xatosi")
        await status.edit_text(f"❌ Serverga saqlashda xato: {e}")
    except Exception:
        log.exception("Kutilmagan xato")
        await status.edit_text("❌ Kutilmagan xato yuz berdi. Administratorga murojaat qiling.")
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                log.warning("Vaqtinchalik faylni o'chirib bo'lmadi: %s", local_path)


@dp.message()
async def other(msg: Message) -> None:
    await msg.answer("Iltimos, fayl yuboring. ID'ingizni bilish uchun: /id")


async def main() -> None:
    if not ALLOWED_IDS:
        log.warning("ALLOWED_USER_IDS bo'sh — hech kim fayl yuklay olmaydi. /id orqali ID'larni yig'ing.")
    await syno.login()  # sozlamalar to'g'riligini darhol tekshiradi
    try:
        await dp.start_polling(bot)
    finally:
        await syno.close()


if __name__ == "__main__":
    asyncio.run(main())
