"""QR Drive Telegram boti — alohida jarayon. Faylni qabul qiladi va navbatga qo'yadi (og'ir ishni worker bajaradi).
Token yoki Bot API server admin paneldan o'zgarsa, bot qayta ishga tushirishsiz yangi sozlama bilan ulanadi."""
from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove, TelegramObject)
from sqlalchemy import select

from .. import settings_store
from ..core.config import config
from ..core.logging import setup_logging
from ..db.models import Employee, FileRecord, TgAccount
from ..db.session import session_scope
from ..services import accounts, qr, system
from ..services.audit import add_audit
from ..services.files import enqueue, refresh_link

log = logging.getLogger("qrdrive.bot")
_HANDLERS: list[tuple[str, Callable[..., Any], tuple[Any, ...]]] = []


def on(kind: str, *filters: Any):
    """Handlerni ro'yxatga yozadi; har bir Dispatcher uchun yangi Router build_router() da yig'iladi."""
    def deco(fn):
        _HANDLERS.append((kind, fn, filters))
        return fn
    return deco


def build_router() -> Router:
    r = Router()
    for kind, fn, filters in _HANDLERS:
        getattr(r, kind).register(fn, *filters)
    return r


def extract_file(msg: Message) -> tuple[str, int | None, str, str] | None:
    """(file_id, hajm, nom, mime)"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if msg.document:
        d = msg.document
        return d.file_id, d.file_size, d.file_name or f"fayl_{ts}", d.mime_type or ""
    if msg.photo:
        p = msg.photo[-1]
        return p.file_id, p.file_size, f"rasm_{ts}.jpg", "image/jpeg"
    if msg.video:
        v = msg.video
        return v.file_id, v.file_size, v.file_name or f"video_{ts}.mp4", v.mime_type or "video/mp4"
    if msg.audio:
        a = msg.audio
        return a.file_id, a.file_size, a.file_name or f"audio_{ts}.mp3", a.mime_type or "audio/mpeg"
    if msg.voice:
        return msg.voice.file_id, msg.voice.file_size, f"ovoz_{ts}.ogg", msg.voice.mime_type or "audio/ogg"
    if msg.video_note:
        return msg.video_note.file_id, msg.video_note.file_size, f"video_{ts}.mp4", "video/mp4"
    if msg.animation:
        a = msg.animation
        return a.file_id, a.file_size, a.file_name or f"animatsiya_{ts}.mp4", a.mime_type or "video/mp4"
    return None


class AccountMiddleware(BaseMiddleware):
    """Har bir xabarda akkauntni yangilaydi (username o'zgarishi tarixga yoziladi), sessiya va sozlamalarni beradi."""

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)
        async with session_scope() as s:
            settings = await settings_store.load(s)
            acc, created = await accounts.touch(s, user.model_dump(), registration=bool(settings.get("registration_required", True)))
            await s.commit()
            data.update(session=s, acc=acc, created=created, settings=settings)
            return await handler(event, data)


def t(settings: dict[str, Any], acc: TgAccount, key: str, **kw: Any) -> str:
    return settings_store.text(settings, acc.lang, key, **kw)


async def gate(msg: Message, s, acc: TgAccount, created: bool, settings: dict[str, Any]) -> bool:
    """Ruxsat tekshiruvi. False — foydalanuvchiga tushuntirish yuborildi."""
    state = await accounts.access_state(s, acc)
    if state == "ok":
        return True
    if state == "registering":
        await msg.answer(t(settings, acc, "reg_welcome" if created else "reg_need"))
        await reg_prompt(msg, s, acc, settings)
        return False
    if state == "pending":
        if created:
            accounts.request_notification(s, acc)
            add_audit(s, "request.new", actor=str(acc.telegram_id), actor_kind="bot", target=acc.display)
            await s.commit()
            await msg.answer(t(settings, acc, "request_sent", id=acc.telegram_id))
        else:
            await msg.answer(t(settings, acc, "request_pending"))
        return False
    await msg.answer(t(settings, acc, "blocked"))
    return False


@on("message", CommandStart())
async def cmd_start(msg: Message, command: CommandObject, session, acc: TgAccount, created: bool, settings: dict[str, Any]):
    code = (command.args or "").strip()
    if code:
        emp = await accounts.redeem_invite(session, acc, code)
        await session.commit()
        if emp:
            await msg.answer(t(settings, acc, "invite_ok", name=emp.full_name))
            return
        await msg.answer(t(settings, acc, "invite_invalid"))
        if acc.status != "active":
            return
    if not await gate(msg, session, acc, created, settings):
        return
    await msg.answer(t(settings, acc, "start", name=acc.first_name or acc.display, max_mb=settings.get("max_file_mb", 100)))


@on("message", Command("id"))
async def cmd_id(msg: Message, acc: TgAccount, settings: dict[str, Any]):
    await msg.answer(t(settings, acc, "your_id", id=acc.telegram_id))


@on("message", Command("help"))
async def cmd_help(msg: Message, acc: TgAccount, settings: dict[str, Any]):
    await msg.answer(t(settings, acc, "help"))


@on("message", Command("lang"))
async def cmd_lang(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="O'zbekcha", callback_data="lang:uz"),
                                                InlineKeyboardButton(text="Русский", callback_data="lang:ru")]])
    await msg.answer("Tilni tanlang / Выберите язык", reply_markup=kb)


@on("callback_query", F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    acc.lang = cb.data.split(":", 1)[1] if cb.data.split(":", 1)[1] in ("uz", "ru") else "uz"
    await session.commit()
    await cb.answer()
    if cb.message:
        await cb.message.edit_text(t(settings, acc, "lang_set"))


# ---------------- ro'yxatdan o'tish ----------------
REG_STEPS = ("name", "phone", "department", "position", "confirm")


async def registering(message: Message, acc: TgAccount | None = None) -> bool:
    """Filtr: foydalanuvchi ro'yxatdan o'tmoqda va bu buyruq emas."""
    return bool(acc and acc.status == "registering" and not (message.text or "").startswith("/"))


def _kb(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


async def reg_prompt(msg: Message, session, acc: TgAccount, settings: dict[str, Any]) -> None:
    """Joriy qadam savolini (kerakli tugmalar bilan) yuboradi."""
    step = acc.reg_state or "name"
    reg = acc.reg_data or {}
    skip = t(settings, acc, "reg_skip")
    if step == "name":
        suggestion = f"{acc.first_name} {acc.last_name}".strip()
        markup = _kb([[KeyboardButton(text=suggestion)]]) if len(suggestion.split()) >= 2 else ReplyKeyboardRemove()
        await msg.answer(t(settings, acc, "reg_name"), reply_markup=markup)
    elif step == "phone":
        await msg.answer(t(settings, acc, "reg_phone"),
                         reply_markup=_kb([[KeyboardButton(text=t(settings, acc, "reg_phone_btn"), request_contact=True)]]))
    elif step == "department":
        depts = sorted({d for d in (await session.execute(select(Employee.department).where(Employee.department != ""))).scalars() if d})[:12]
        rows = [[KeyboardButton(text=d) for d in depts[i:i + 2]] for i in range(0, len(depts), 2)] + [[KeyboardButton(text=skip)]]
        await msg.answer(t(settings, acc, "reg_department"), reply_markup=_kb(rows))
    elif step == "position":
        await msg.answer(t(settings, acc, "reg_position"), reply_markup=_kb([[KeyboardButton(text=skip)]]))
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(settings, acc, "reg_yes"), callback_data="reg:ok"),
                                                    InlineKeyboardButton(text=t(settings, acc, "reg_edit"), callback_data="reg:edit")]])
        await msg.answer(t(settings, acc, "reg_confirm", name=reg.get("full_name", "—"), phone=acc.phone or "—",
                           department=reg.get("department") or "—", position=reg.get("position") or "—"), reply_markup=kb)


def _phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return "+" + digits if digits else ""


@on("message", registering)
async def reg_input(msg: Message, session, acc: TgAccount, settings: dict[str, Any]):
    step = acc.reg_state or "name"
    data = dict(acc.reg_data or {})
    text = (msg.text or "").strip()
    skip = t(settings, acc, "reg_skip")
    if step == "phone":
        contact = msg.contact
        if contact is None or (contact.user_id and contact.user_id != msg.from_user.id):
            await msg.answer(t(settings, acc, "reg_phone_wrong"))
            return await reg_prompt(msg, session, acc, settings)
        acc.phone = _phone(contact.phone_number)
        nxt = "department"
    elif not text:  # fayl, stiker va h.k. — avval ro'yxatdan o'tish
        await msg.answer(t(settings, acc, "reg_need"))
        return await reg_prompt(msg, session, acc, settings)
    elif step == "name":
        if len(text.split()) < 2 or len(text) > 150:
            await msg.answer(t(settings, acc, "reg_name_short"))
            return
        data["full_name"] = " ".join(text.split())
        nxt = "phone"
    elif step in ("department", "position"):
        data[step] = "" if text == skip else text[:200]
        nxt = "position" if step == "department" else "confirm"
    else:  # confirm — tugmani bosish kutilmoqda
        return await reg_prompt(msg, session, acc, settings)
    acc.reg_data, acc.reg_state = data, nxt
    await session.commit()
    if nxt == "confirm":
        await msg.answer("👍", reply_markup=ReplyKeyboardRemove())
    await reg_prompt(msg, session, acc, settings)


async def collect_profile(bot: Bot, acc: TgAccount) -> None:
    """Telegram profilini to'liq saqlash: getChat (bio, tug'ilgan sana, shaxsiy kanal...) va profil rasmi."""
    profile = dict(acc.profile or {})
    try:
        chat = await bot.get_chat(acc.telegram_id)
        data = chat.model_dump(mode="json", exclude_none=True)
        data.pop("photo", None)
        profile["chat"] = data
    except Exception:  # noqa: BLE001 — majburiy emas
        pass
    try:
        photos = await bot.get_user_profile_photos(acc.telegram_id, limit=1)
        if photos.total_count and photos.photos:
            folder = config.assets_dir / "avatars"
            folder.mkdir(parents=True, exist_ok=True)
            await bot.download(photos.photos[0][-1].file_id, destination=folder / f"{acc.telegram_id}.jpg")
            acc.photo = f"{acc.telegram_id}.jpg"
    except Exception:  # noqa: BLE001
        pass
    acc.profile = profile


@on("callback_query", F.data.startswith("reg:"))
async def reg_callback(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any], bot: Bot):
    await cb.answer()
    if acc.status != "registering" or not cb.message:
        return
    if cb.data == "reg:edit":
        acc.reg_state, acc.reg_data = "name", {}
        await session.commit()
        await cb.message.edit_reply_markup(reply_markup=None)
        return await reg_prompt(cb.message, session, acc, settings)
    if cb.data != "reg:ok" or acc.reg_state != "confirm":
        return
    await collect_profile(bot, acc)
    acc.status, acc.reg_state, acc.registered_at = "pending", "", datetime.now(timezone.utc)
    accounts.request_notification(session, acc)
    add_audit(session, "request.new", actor=str(acc.telegram_id), actor_kind="bot", target=(acc.reg_data or {}).get("full_name") or acc.display,
              details={"phone": acc.phone, **{k: v for k, v in (acc.reg_data or {}).items() if k != "full_name"}})
    await session.commit()
    await cb.message.edit_text(t(settings, acc, "reg_sent"))


@on("message", Command("myfiles"))
async def cmd_myfiles(msg: Message, session, acc: TgAccount, created: bool, settings: dict[str, Any]):
    if not await gate(msg, session, acc, created, settings):
        return
    rows = (await session.execute(select(FileRecord).where(
        FileRecord.employee_id == acc.employee_id, FileRecord.deleted_at.is_(None), FileRecord.status == "delivered")
        .order_by(FileRecord.id.desc()).limit(10))).scalars().all()
    if not rows:
        await msg.answer(t(settings, acc, "myfiles_empty"))
        return
    lines, buttons = [t(settings, acc, "myfiles_title")], []
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r.original_name} — {r.created_at:%d.%m.%Y}")
        buttons.append([InlineKeyboardButton(text=f"📷 {i}. QR", callback_data=f"qr:{r.id}"),
                        InlineKeyboardButton(text=f"🔄 {i}. Havola", callback_data=f"rl:{r.id}")])
    await msg.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def _own_file(session, acc: TgAccount, data: str) -> FileRecord | None:
    try:
        fid = int(data.split(":", 1)[1])
    except ValueError:
        return None
    rec = await session.get(FileRecord, fid)
    if rec is None or rec.employee_id != acc.employee_id or rec.deleted_at is not None or await accounts.access_state(session, acc) != "ok":
        return None
    return rec


async def _send_qr(cb: CallbackQuery, rec: FileRecord, settings: dict[str, Any], acc: TgAccount, extra: str = "") -> None:
    style = settings.get("qr_style") or {}
    image = qr.png(rec.link_url, style, qr.caption_for(style, rec.original_name, settings.get("company_name", "")))
    caption = t(settings, acc, "done", path=rec.remote_path, url=rec.link_url)
    await cb.message.answer_photo(BufferedInputFile(image, "qr.png"), caption=(extra + "\n" + caption).strip())


@on("callback_query", F.data.startswith("qr:"))
async def cb_qr(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    rec = await _own_file(session, acc, cb.data)
    await cb.answer()
    if rec and rec.link_url and cb.message:
        await _send_qr(cb, rec, settings, acc)


@on("callback_query", F.data.startswith("rl:"))
async def cb_refresh(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    rec = await _own_file(session, acc, cb.data)
    await cb.answer()
    if not rec or not cb.message:
        return
    try:
        await refresh_link(session, rec, settings)
        add_audit(session, "file.link_refresh", actor=str(acc.telegram_id), actor_kind="bot", target=rec.original_name)
        await session.commit()
    except Exception:  # noqa: BLE001
        log.exception("havolani yangilab bo'lmadi")
        await cb.message.answer(t(settings, acc, "failed", reason="—"))
        return
    await _send_qr(cb, rec, settings, acc, t(settings, acc, "link_refreshed"))


@on("message", F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation)
async def on_file(msg: Message, session, acc: TgAccount, created: bool, settings: dict[str, Any]):
    if not await gate(msg, session, acc, created, settings):
        return
    file_id, size, name, mime = extract_file(msg)
    max_mb = int(settings.get("max_file_mb") or 100)
    if size and size > max_mb * 1024 * 1024:
        await msg.answer(t(settings, acc, "too_big", size=f"{size / 1024 / 1024:.1f}", max_mb=max_mb))
        return
    from ..services.pipeline import allowed
    if not allowed(name, settings.get("allowed_types", "")):
        await msg.answer(t(settings, acc, "type_not_allowed", types=settings.get("allowed_types", "")))
        return
    mode = settings.get("visibility_mode") or "ask"
    ask = mode == "ask"
    status = await msg.reply(t(settings, acc, "choose_visibility", name=name) if ask else t(settings, acc, "received"))
    rec = await enqueue(session, source="telegram", original_name=name, actor=acc.display, employee_id=acc.employee_id,
                        account_id=acc.id, size=size, mime=mime, caption=msg.caption or "",
                        options={} if ask else {"visibility": mode if mode in ("public", "private") else "public"},
                        tg={"chat_id": msg.chat.id, "file_id": file_id, "status_msg_id": status.message_id}, awaiting=ask)
    await session.commit()
    if ask:  # foydalanuvchi havola turini tanlaydi: Public yoki Private
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(settings, acc, "btn_public"), callback_data=f"vis:{rec.id}:public"),
            InlineKeyboardButton(text=t(settings, acc, "btn_private"), callback_data=f"vis:{rec.id}:private")]])
        await status.edit_reply_markup(reply_markup=kb)
    log.info("fayl qabul qilindi", extra={"data": {"id": rec.id, "size": size, "awaiting": ask}})


@on("callback_query", F.data.startswith("vis:"))
async def cb_visibility(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    """Havola turi tanlandi: fayl navbatga qo'yiladi (worker yuklaydi va tanlangan turdagi havolani yaratadi)."""
    try:
        _, fid, vis = cb.data.split(":")
        rec = await session.get(FileRecord, int(fid))
    except (ValueError, TypeError):
        rec, vis = None, ""
    if rec is None or rec.account_id != acc.id or vis not in ("public", "private"):
        await cb.answer()
        return
    if rec.status != "awaiting":  # allaqachon tanlangan yoki vaqt o'tib standart tur qo'llangan
        await cb.answer()
        return
    rec.options = {**(rec.options or {}), "visibility": vis}
    rec.status, rec.next_attempt_at = "queued", datetime.now(timezone.utc)
    add_audit(session, "file.visibility", actor=str(acc.telegram_id), actor_kind="bot", target=rec.original_name, details={"visibility": vis})
    await session.commit()
    await cb.answer(t(settings, acc, f"vis_{vis}"))
    if cb.message:
        await cb.message.edit_text(t(settings, acc, "vis_chosen", vis=t(settings, acc, f"vis_{vis}")))


@on("message")
async def other(msg: Message, session, acc: TgAccount, created: bool, settings: dict[str, Any]):
    if not await gate(msg, session, acc, created, settings):
        return
    await msg.answer(t(settings, acc, "send_file"))


def make_bot(settings: dict[str, Any]) -> Bot:
    api_url = (settings.get("bot_api_url") or "").strip()
    if api_url:
        session = AiohttpSession(api=TelegramAPIServer.from_base(api_url, is_local=bool(settings.get("bot_api_local"))))
        return Bot(settings["bot_token"], session=session)
    return Bot(settings["bot_token"])


class BotService:
    def __init__(self) -> None:
        self.stop = asyncio.Event()
        self.started = datetime.now(timezone.utc)
        self.dp = Dispatcher()
        self.dp.message.outer_middleware(AccountMiddleware())
        self.dp.callback_query.outer_middleware(AccountMiddleware())
        self.dp.include_router(build_router())
        self.state: dict[str, Any] = {"status": "starting"}

    async def _settings(self) -> dict[str, Any]:
        async with session_scope() as s:
            return await settings_store.load(s, fresh=True)

    async def _watch(self, signature: tuple) -> None:
        """Sozlama o'zgarsa polling to'xtatiladi — tashqi halqa yangi token bilan qayta ulanadi."""
        while not self.stop.is_set():
            await asyncio.sleep(5)
            with suppress(Exception):
                s = await self._settings()
                if (s.get("bot_token"), s.get("bot_api_url"), bool(s.get("bot_api_local"))) != signature:
                    log.info("bot sozlamasi o'zgardi — qayta ulanilmoqda")
                    break
        with suppress(Exception):
            await self.dp.stop_polling()

    async def _beat(self) -> None:
        while not self.stop.is_set():
            with suppress(Exception):
                await system.beat("bot", self.state)
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop.wait(), timeout=20)

    async def run(self) -> None:
        await system.bootstrap()
        await system.beat("bot", self.state, started=self.started)
        beat = asyncio.create_task(self._beat())
        while not self.stop.is_set():
            settings = await self._settings()
            signature = (settings.get("bot_token"), settings.get("bot_api_url"), bool(settings.get("bot_api_local")))
            if not settings.get("bot_token"):
                self.state = {"status": "no_token"}
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.stop.wait(), timeout=5)
                continue
            bot = make_bot(settings)
            watcher = asyncio.create_task(self._watch(signature))
            try:
                me = await bot.get_me()
                self.state = {"status": "polling", "username": me.username}
                log.info("bot ulandi: @%s", me.username)
                await self.dp.start_polling(bot, handle_signals=False, allowed_updates=["message", "callback_query"])
            except Exception as e:  # noqa: BLE001
                self.state = {"status": "error", "error": type(e).__name__}
                log.error("bot ulanmadi: %s", type(e).__name__)
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.stop.wait(), timeout=15)
            finally:
                watcher.cancel()
                with suppress(Exception):
                    await bot.session.close()
        beat.cancel()

    def shutdown(self) -> None:
        self.stop.set()
        with suppress(Exception):
            asyncio.get_running_loop().create_task(self.dp.stop_polling())


def run() -> None:
    setup_logging("bot", config.log_level)
    service = BotService()

    async def main() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, service.shutdown)
        await service.run()

    with suppress(KeyboardInterrupt):
        asyncio.run(main())


if __name__ == "__main__":
    run()
