"""QR Drive Telegram boti — alohida jarayon. Faylni qabul qiladi va navbatga qo'yadi (og'ir ishni worker bajaradi).
Token yoki Bot API server admin paneldan o'zgarsa, bot qayta ishga tushirishsiz yangi sozlama bilan ulanadi."""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, BotCommandScopeChat, BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyParameters,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove, TelegramObject)
from sqlalchemy import func, select

from .. import settings_store
from ..core.config import config
from ..core.logging import setup_logging
from ..db.models import Employee, FileRecord, TgAccount
from ..db.session import session_scope
from ..services import accounts, admins, qr, system, uploads
from ..services.audit import add_audit, notify
from ..services.archive import is_archive
from ..services.files import enqueue, find_previous, refresh_link
from ..services.naming import safe_name

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
            await admins.ensure_admin_access(s, acc, settings)  # admin ro'yxatdan o'tish va tasdiqlashni kutmaydi
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
        await msg.reply(t(settings, acc, "reg_welcome" if created else "reg_need"))
        await reg_prompt(msg, s, acc, settings)
        return False
    if state == "pending":
        if created:
            add_audit(s, "request.new", actor=str(acc.telegram_id), actor_kind="bot", target=acc.display)
            if await admins.auto_approve(s, acc, settings):
                await s.commit()
                await msg.reply(t(settings, acc, "approved"))
                return True
            accounts.request_notification(s, acc)
            await s.commit()
            await msg.reply(t(settings, acc, "request_sent", id=acc.telegram_id))
        else:
            await msg.reply(t(settings, acc, "request_pending"))
        return False
    await msg.reply(t(settings, acc, "blocked"))
    return False


@on("message", CommandStart())
async def cmd_start(msg: Message, command: CommandObject, session, acc: TgAccount, created: bool, settings: dict[str, Any]):
    code = (command.args or "").strip()
    if code:
        emp = await accounts.redeem_invite(session, acc, code)
        await session.commit()
        if emp:
            await msg.reply(t(settings, acc, "invite_ok", name=emp.full_name))
            return
        await msg.reply(t(settings, acc, "invite_invalid"))
        if acc.status != "active":
            return
    if not await gate(msg, session, acc, created, settings):
        return
    text = t(settings, acc, "start", name=acc.first_name or acc.display, max_mb=settings.get("max_file_mb", 100))
    if admins.is_admin(acc, settings):
        text += "\n\n" + ADMIN_HELP
        with suppress(Exception):  # admin buyruqlari shu chat menyusida ko'rinadi
            await msg.bot.set_my_commands(BASE_COMMANDS + ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=msg.chat.id))
    await msg.reply(text)


@on("message", Command("id"))
async def cmd_id(msg: Message, acc: TgAccount, settings: dict[str, Any]):
    await msg.reply(t(settings, acc, "your_id", id=acc.telegram_id))


@on("message", Command("help"))
async def cmd_help(msg: Message, acc: TgAccount, settings: dict[str, Any]):
    text = t(settings, acc, "help")
    if admins.is_admin(acc, settings):
        text += "\n\n" + ADMIN_HELP
    await msg.reply(text)


@on("message", Command("lang"))
async def cmd_lang(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="O'zbekcha", callback_data="lang:uz"),
                                                InlineKeyboardButton(text="Русский", callback_data="lang:ru")]])
    await msg.reply("Tilni tanlang / Выберите язык", reply_markup=kb)


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
        await msg.reply(t(settings, acc, "reg_name"), reply_markup=markup)
    elif step == "phone":
        await msg.reply(t(settings, acc, "reg_phone"),
                         reply_markup=_kb([[KeyboardButton(text=t(settings, acc, "reg_phone_btn"), request_contact=True)]]))
    elif step == "department":
        depts = sorted({d for d in (await session.execute(select(Employee.department).where(Employee.department != ""))).scalars() if d})[:12]
        rows = [[KeyboardButton(text=d) for d in depts[i:i + 2]] for i in range(0, len(depts), 2)] + [[KeyboardButton(text=skip)]]
        await msg.reply(t(settings, acc, "reg_department"), reply_markup=_kb(rows))
    elif step == "position":
        await msg.reply(t(settings, acc, "reg_position"), reply_markup=_kb([[KeyboardButton(text=skip)]]))
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(settings, acc, "reg_yes"), callback_data="reg:ok"),
                                                    InlineKeyboardButton(text=t(settings, acc, "reg_edit"), callback_data="reg:edit")]])
        await msg.reply(t(settings, acc, "reg_confirm", name=reg.get("full_name", "—"), phone=acc.phone or "—",
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
            await msg.reply(t(settings, acc, "reg_phone_wrong"))
            return await reg_prompt(msg, session, acc, settings)
        acc.phone = _phone(contact.phone_number)
        nxt = "department"
    elif not text:  # fayl, stiker va h.k. — avval ro'yxatdan o'tish
        await msg.reply(t(settings, acc, "reg_need"))
        return await reg_prompt(msg, session, acc, settings)
    elif step == "name":
        if len(text.split()) < 2 or len(text) > 150:
            await msg.reply(t(settings, acc, "reg_name_short"))
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
        await msg.reply("👍", reply_markup=ReplyKeyboardRemove())
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
    add_audit(session, "request.new", actor=str(acc.telegram_id), actor_kind="bot", target=(acc.reg_data or {}).get("full_name") or acc.display,
              details={"phone": acc.phone, **{k: v for k, v in (acc.reg_data or {}).items() if k != "full_name"}})
    if await admins.auto_approve(session, acc, settings):
        await session.commit()
        await cb.message.edit_text(t(settings, acc, "approved"))
        return
    accounts.request_notification(session, acc)
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
        await msg.reply(t(settings, acc, "myfiles_empty"))
        return
    lines, buttons = [t(settings, acc, "myfiles_title")], []
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r.original_name} — {r.created_at:%d.%m.%Y}")
        buttons.append([InlineKeyboardButton(text=f"📷 {i}. QR", callback_data=f"qr:{r.id}"),
                        InlineKeyboardButton(text=f"🔄 {i}. Havola", callback_data=f"rl:{r.id}")])
    await msg.reply("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


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
    await cb.message.reply_photo(BufferedInputFile(image, "qr.png"), caption=(extra + "\n" + caption).strip())


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
        await cb.message.reply(t(settings, acc, "failed", reason="—"))
        return
    await _send_qr(cb, rec, settings, acc, t(settings, acc, "link_refreshed"))


@on("message", F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.animation)
async def on_file(msg: Message, session, acc: TgAccount, created: bool, settings: dict[str, Any], bot: Bot):
    if not await gate(msg, session, acc, created, settings):
        return
    file_id, size, name, mime = extract_file(msg)
    max_mb = int(settings.get("max_file_mb") or 100)
    if size and size > max_mb * 1024 * 1024:
        await msg.reply(t(settings, acc, "too_big", size=f"{size / 1024 / 1024:.1f}", max_mb=max_mb))
        return
    from ..services.pipeline import allowed
    if not allowed(name, settings.get("allowed_types", "")):
        await msg.reply(t(settings, acc, "type_not_allowed", types=settings.get("allowed_types", "")))
        return
    if not uploads.bot_can_download(size, settings):
        # Rasmiy Bot API 20 MB dan katta faylni bermaydi — bir martalik veb-yuklash havolasi
        ticket = await uploads.create_ticket(session, acc, msg.chat.id, name, size, msg.caption or "", reply_to=msg.message_id)
        await session.commit()
        url = uploads.ticket_url(settings, ticket)
        text = t(settings, acc, "big_file", size=f"{size / 1024 / 1024:.1f}", url=url, hours=uploads.TICKET_HOURS)
        try:
            await msg.reply(text, reply_markup=_ikb_url(t(settings, acc, "btn_upload"), url))
        except Exception:  # noqa: BLE001 — Telegram ba'zi manzillarni (localhost) tugmada qabul qilmaydi
            await msg.reply(text)
        log.info("katta fayl — veb-yuklash havolasi berildi", extra={"data": {"size": size}})
        return
    rec = await enqueue(session, source="telegram", original_name=name, actor=acc.display, employee_id=acc.employee_id,
                        account_id=acc.id, size=size, mime=mime, caption=msg.caption or "",
                        options={"pending": True, "tg_msg_id": msg.message_id},
                        tg={"chat_id": msg.chat.id, "file_id": file_id, "status_msg_id": None}, awaiting=True)
    await session.commit()
    first = await batcher.add(bot, acc.id, msg.chat.id, rec.id, name)
    if first:
        with suppress(Exception):
            await bot.send_chat_action(msg.chat.id, "upload_document")
    log.info("fayl qabul qilindi", extra={"data": {"id": rec.id, "size": size}})


class Batcher:
    """Ketma-ket kelgan fayllarni (albom, birga tanlangan fayllar) bitta guruhga yig'adi:
    oxirgi fayldan keyin WINDOW soniya o'tgach bitta savol beriladi. Kutish paytida worker fayllarni oldindan yuklab oladi."""
    WINDOW = 1.0

    def __init__(self) -> None:
        self.pending: dict[int, dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()

    async def add(self, bot: Bot, acc_id: int, chat_id: int, rec_id: int, name: str) -> bool:
        async with self.lock:
            group = self.pending.get(acc_id)
            first = group is None
            if first:
                group = {"ids": [], "names": [], "chat": chat_id, "last": 0.0}
                self.pending[acc_id] = group
                task = asyncio.create_task(self._close_later(bot, acc_id))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
            group["ids"].append(rec_id)
            group["names"].append(name)
            group["last"] = time.monotonic()
            return first

    async def _close_later(self, bot: Bot, acc_id: int) -> None:
        while True:
            await asyncio.sleep(min(0.2, self.WINDOW / 2))
            async with self.lock:
                group = self.pending[acc_id]
                if time.monotonic() - group["last"] >= self.WINDOW:
                    del self.pending[acc_id]
                    break
        try:
            await close_group(bot, acc_id, group)
        except Exception:  # noqa: BLE001
            log.exception("guruhni yopishda xato")


batcher = Batcher()


def _reply_opt(rec: FileRecord) -> dict[str, Any]:
    mid = (rec.options or {}).get("tg_msg_id")
    return {"tg_msg_id": mid} if mid else {}


def _reply_to(rec: FileRecord) -> ReplyParameters | None:
    mid = (rec.options or {}).get("tg_msg_id")
    return ReplyParameters(message_id=int(mid), allow_sending_without_reply=True) if mid else None


def _ikb_url(label: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]])


def _ikb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in rows])


async def close_group(bot: Bot, acc_id: int, group: dict[str, Any]) -> None:
    """Guruh yopildi: bitta fayl — odatiy savollar; bir nechta — «bitta papka» yoki «har biri alohida»."""
    async with session_scope() as session:
        acc = await session.get(TgAccount, acc_id)
        settings = await settings_store.load(session)
        recs = [r for r in [await session.get(FileRecord, i) for i in group["ids"]] if r is not None and r.status == "awaiting"]
        if acc is None or not recs:
            return
        now = datetime.now(timezone.utc)
        reply = _reply_to(recs[0])  # savol/holat xabari foydalanuvchi yuborgan faylga javob (reply) bo'ladi
        if len(recs) == 1:
            rec = recs[0]
            plan = await plan_choices(session, acc, settings, rec.original_name)
            rec.options = {**{k: v for k, v in (rec.options or {}).items() if k != "pending"}, **plan["options"]}
            if plan["rows"]:
                kb = _ikb([[(label, f"ch:{rec.id}:{action}:{vis}") for label, action, vis in row] for row in plan["rows"]])
                sent = await bot.send_message(group["chat"], plan["text"], reply_markup=kb, reply_parameters=reply)
            else:
                sent = await bot.send_message(group["chat"], t(settings, acc, "received"), reply_parameters=reply)
                rec.status, rec.next_attempt_at = "queued", now
            rec.tg_status_msg_id = sent.message_id
            await session.commit()
            return
        vis_mode = settings.get("visibility_mode") or "ask"
        vis_opts = [("public", "🌐"), ("private", "🔒")] if vis_mode == "ask" else [("-", "")]
        multi = settings.get("multi_mode") or "ask"
        first = recs[0]
        first.options = {**(first.options or {}), "batch_children": [r.id for r in recs]}
        if multi in ("folder", "separate"):
            await session.commit()
            vis = vis_mode if vis_mode in ("public", "private") else "-"
            sent = await bot.send_message(group["chat"], t(settings, acc, "received"), reply_parameters=reply)
            await apply_group(session, acc, settings, first, multi, vis, sent.message_id)
            return
        names = "\n".join(f"• {n}" for n in group["names"][:10])
        if len(group["names"]) > 10:
            names += "\n" + t(settings, acc, "batch_more", n=len(group["names"]) - 10)
        rows = [[(f"{t(settings, acc, 'btn_one_folder')} {icon}".strip(), f"bt:{first.id}:folder:{v}") for v, icon in vis_opts],
                [(f"{t(settings, acc, 'btn_separate')} {icon}".strip(), f"bt:{first.id}:separate:{v}") for v, icon in vis_opts]]
        await session.commit()
        await bot.send_message(group["chat"], t(settings, acc, "ask_batch", n=len(recs), names=names), reply_markup=_ikb(rows),
                               reply_parameters=reply)


async def apply_group(session, acc: TgAccount, settings: dict[str, Any], first: FileRecord, mode: str, vis: str,
                      status_msg_id: int | None) -> FileRecord | None:
    """Guruh uchun tanlov: bitta papka (yangi «folder» yozuv) yoki har bir fayl alohida navbatga."""
    ids = [int(i) for i in (first.options or {}).get("batch_children") or [first.id]]
    recs = [r for r in [await session.get(FileRecord, i) for i in ids] if r is not None and r.status == "awaiting"]
    if not recs:
        return None
    now = datetime.now(timezone.utc)
    extra = {"visibility": vis} if vis in ("public", "private") else {}
    folder = None
    if mode == "folder":
        caption = next((r.caption for r in recs if r.caption), "")
        folder = await enqueue(session, source="telegram", original_name=safe_name(caption[:60]) if caption else f"Fayllar ({len(recs)})",
                               actor=acc.display, employee_id=acc.employee_id, account_id=acc.id,
                               options={"batch_children": [r.id for r in recs], **extra, **_reply_opt(recs[0])},
                               tg={"chat_id": recs[0].tg_chat_id, "file_id": "", "status_msg_id": status_msg_id})
        for r in recs:
            r.status = "merged"
    else:
        for i, r in enumerate(recs):
            opts = {k: v for k, v in (r.options or {}).items() if k not in ("pending", "batch_children")}
            r.options = {**opts, **extra}
            r.status, r.next_attempt_at = "queued", now
            if i == 0 and status_msg_id:
                r.tg_status_msg_id = status_msg_id
    add_audit(session, "file.group_choice", actor=str(acc.telegram_id), actor_kind="bot",
              target=f"{len(recs)} ta fayl", details={"mode": mode, "visibility": vis})
    await session.commit()
    return folder


@on("callback_query", F.data.startswith("bt:"))
async def cb_group(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    parts = cb.data.split(":")
    first = await session.get(FileRecord, int(parts[1])) if len(parts) == 4 and parts[1].isdigit() else None
    if first is None or first.account_id != acc.id or first.status != "awaiting" or parts[2] not in ("folder", "separate"):
        return await cb.answer()
    await apply_group(session, acc, settings, first, parts[2], parts[3], cb.message.message_id if cb.message else None)
    await cb.answer()
    if cb.message:
        label = t(settings, acc, "btn_one_folder" if parts[2] == "folder" else "btn_separate")
        if parts[3] in ("public", "private"):
            label += " · " + t(settings, acc, f"vis_{parts[3]}")
        await cb.message.edit_text(t(settings, acc, "chosen", choice=label))


async def plan_choices(session, acc: TgAccount, settings: dict[str, Any], name: str) -> dict[str, Any]:
    """Qaysi savollarni berish kerak: fayl yangilanishi (shu nom avval yuklangan), arxiv (papka qilish), havola turi.
    Hammasi bitta xabarda, kombinatsiyalangan tugmalar bilan."""
    vis_mode = settings.get("visibility_mode") or "ask"
    ask_vis = vis_mode == "ask"
    vis_opts = [("public", "🌐"), ("private", "🔒")] if ask_vis else [("-", "")]
    options: dict[str, Any] = {} if ask_vis else {"visibility": vis_mode if vis_mode in ("public", "private") else "public"}
    prev = await find_previous(session, employee_id=acc.employee_id, api_key_id=None, name=name)
    replace_mode = settings.get("replace_mode") or "ask"
    if prev is not None and replace_mode == "replace":
        options["replace_of"] = prev.id
        return {"text": "", "rows": [], "options": options}
    if prev is not None and replace_mode == "ask":
        date = f"{prev.created_at:%d.%m.%Y %H:%M}" if prev.created_at else ""
        new_row = [(f"{t(settings, acc, 'btn_new')} {icon}".strip(), "new", v) for v, icon in vis_opts]
        return {"text": t(settings, acc, "ask_replace", name=name, date=date),
                "rows": [[(t(settings, acc, "btn_replace"), f"replace{prev.id}", "-")], new_row], "options": options}
    archive_mode = settings.get("archive_mode") or "ask"
    if is_archive(name) and archive_mode == "folder":
        options["archive"] = "folder"
    if is_archive(name) and archive_mode == "ask":
        rows = [[(f"{t(settings, acc, 'btn_archive')} {icon}".strip(), "archive", v) for v, icon in vis_opts],
                [(f"{t(settings, acc, 'btn_folder')} {icon}".strip(), "folder", v) for v, icon in vis_opts]]
        return {"text": t(settings, acc, "ask_archive", name=name), "rows": rows, "options": options}
    if ask_vis:
        return {"text": t(settings, acc, "choose_visibility", name=name),
                "rows": [[(t(settings, acc, "btn_public"), "file", "public"), (t(settings, acc, "btn_private"), "file", "private")]],
                "options": options}
    return {"text": "", "rows": [], "options": options}


async def apply_choice(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any], fid: str, action: str, vis: str) -> None:
    try:
        rec = await session.get(FileRecord, int(fid))
    except (ValueError, TypeError):
        rec = None
    if rec is None or rec.account_id != acc.id or rec.status != "awaiting":  # begona yoki allaqachon tanlangan
        await cb.answer()
        return
    opts = {k: v for k, v in (rec.options or {}).items() if k != "pending"}
    labels = []
    if action.startswith("replace"):
        opts["replace_of"] = int(action[len("replace"):])
        labels.append(t(settings, acc, "btn_replace"))
    elif action in ("archive", "folder"):
        opts["archive"] = action
        labels.append(t(settings, acc, f"btn_{action}"))
    elif action == "new":
        labels.append(t(settings, acc, "btn_new"))
    if vis in ("public", "private"):
        opts["visibility"] = vis
        labels.append(t(settings, acc, f"vis_{vis}"))
    rec.options = opts
    rec.status, rec.next_attempt_at = "queued", datetime.now(timezone.utc)
    add_audit(session, "file.choice", actor=str(acc.telegram_id), actor_kind="bot", target=rec.original_name,
              details={"action": action, "visibility": vis})
    await session.commit()
    await cb.answer()
    if cb.message:
        await cb.message.edit_text(t(settings, acc, "chosen", choice=" · ".join(labels)))


@on("callback_query", F.data.startswith("ch:"))
async def cb_choice(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    parts = cb.data.split(":")
    if len(parts) != 4:
        return await cb.answer()
    await apply_choice(cb, session, acc, settings, parts[1], parts[2], parts[3])


@on("callback_query", F.data.startswith("vis:"))
async def cb_visibility(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    """Eski xabarlardagi tugmalar (faqat havola turi) uchun moslik."""
    parts = cb.data.split(":")
    if len(parts) != 3:
        return await cb.answer()
    await apply_choice(cb, session, acc, settings, parts[1], "file", parts[2])


# ---------------- bot adminlari ----------------
ADMIN_HELP = ("👑 Admin buyruqlari:\n/stats — tizim holati\n/pending — kutilayotgan so'rovlar (tasdiqlash tugmalari bilan)\n"
              "/mode — tasdiqlash rejimi (avtomatik / qo'lda)\n\nYangi so'rovlar, saqlangan fayllar, xatolar va "
              "saqlash joyi holati shu chatga avtomatik keladi.")
BASE_COMMANDS = [BotCommand(command="start", description="Boshlash"), BotCommand(command="myfiles", description="Oxirgi fayllarim"),
                 BotCommand(command="id", description="Telegram ID"), BotCommand(command="lang", description="Til / Язык"),
                 BotCommand(command="help", description="Yordam")]
ADMIN_COMMANDS = [BotCommand(command="stats", description="Tizim holati"),
                  BotCommand(command="pending", description="Kutilayotgan so'rovlar"),
                  BotCommand(command="mode", description="Tasdiqlash rejimi")]
MODE_LABEL = {"auto": "🤖 Avtomatik — ro'yxatdan o'tgan foydalanuvchi darhol faollashadi",
              "manual": "👤 Qo'lda — har bir so'rovni admin tasdiqlaydi"}


def _decision_kb(acc_id: int) -> InlineKeyboardMarkup:
    return _ikb([[("✅ Tasdiqlash", f"adm:ok:{acc_id}"), ("❌ Rad etish", f"adm:no:{acc_id}")],
                 [("⛔ Bloklash", f"adm:block:{acc_id}")]])


async def admin_only(event: Message | CallbackQuery, acc: TgAccount | None = None, settings: dict[str, Any] | None = None) -> bool:
    return admins.is_admin(acc, settings or {})


@on("message", Command("admin"), admin_only)
async def cmd_admin(msg: Message):
    await msg.reply(ADMIN_HELP)


@on("message", Command("stats"), admin_only)
async def cmd_stats(msg: Message, session):
    await msg.reply(await admins.stats_text(session))


@on("message", Command("pending"), admin_only)
async def cmd_pending(msg: Message, session):
    rows = (await session.execute(select(TgAccount).where(TgAccount.status == "pending")
                                  .order_by(TgAccount.id.desc()).limit(10))).scalars().all()
    if not rows:
        return await msg.reply("✅ Kutilayotgan so'rov yo'q.")
    await msg.reply(f"⏳ Kutilayotgan so'rovlar: {len(rows)}" + (" (oxirgi 10 tasi)" if len(rows) == 10 else ""))
    for a in rows:
        await msg.reply(accounts.describe(a), reply_markup=_decision_kb(a.id))


def _mode_kb(current: str) -> InlineKeyboardMarkup:
    return _ikb([[(("● " if current == m else "") + MODE_LABEL[m].split(" — ")[0], f"mode:{m}")] for m in admins.MODES])


@on("message", Command("mode"), admin_only)
async def cmd_mode(msg: Message, settings: dict[str, Any]):
    current = settings.get("approval_mode") or "manual"
    await msg.reply(f"Tasdiqlash rejimi:\n{MODE_LABEL.get(current, current)}", reply_markup=_mode_kb(current))


@on("callback_query", F.data.startswith("mode:"), admin_only)
async def cb_mode(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any]):
    mode = cb.data.split(":", 1)[1]
    if mode not in admins.MODES:
        return await cb.answer()
    changes = await settings_store.save(session, {"approval_mode": mode})
    if changes:
        add_audit(session, "settings.update", actor=f"@{acc.username or acc.telegram_id}", actor_kind="bot",
                  target="approval_mode", details={"approval_mode": list(changes["approval_mode"])})
        await session.commit()
    await cb.answer("Saqlandi")
    pending = (await session.execute(select(func.count()).select_from(TgAccount).where(TgAccount.status == "pending"))).scalar_one()
    note = f"\n\nℹ️ {pending} ta eski so'rov kutmoqda — /pending" if mode == "auto" and pending else ""
    if cb.message:
        with suppress(Exception):
            await cb.message.edit_text(f"Tasdiqlash rejimi:\n{MODE_LABEL[mode]}{note}", reply_markup=_mode_kb(mode))


@on("callback_query", F.data.startswith("adm:"), admin_only)
async def cb_decision(cb: CallbackQuery, session, acc: TgAccount, settings: dict[str, Any], bot: Bot):
    parts = cb.data.split(":")
    target = await session.get(TgAccount, int(parts[2])) if len(parts) == 3 and parts[2].isdigit() else None
    if target is None or parts[1] not in ("ok", "no", "block"):
        return await cb.answer()
    if target.status != "pending":
        await cb.answer("Bu so'rov allaqachon ko'rib chiqilgan", show_alert=True)
        if cb.message:
            with suppress(Exception):
                await cb.message.edit_reply_markup(reply_markup=None)
        return
    actor = f"@{acc.username}" if acc.username else str(acc.telegram_id)
    if parts[1] == "ok":
        emp = await accounts.approve_as_new(session, target, actor, {})
        short, result = "✅ Tasdiqlandi", f"✅ Tasdiqlandi ({actor}) · papka: {emp.folder}"
        notify(session, "access_approved", f"Tasdiqlandi: {emp.full_name}", f"Admin: {actor}", level="success",
               audience="bot", link="/qr/employees")
    else:
        block = parts[1] == "block"
        target.status = "blocked" if block else "rejected"
        add_audit(session, "request.blocked" if block else "request.rejected", actor=actor, actor_kind="bot", target=target.display)
        short = "⛔ Bloklandi" if block else "❌ Rad etildi"
        result = f"{short} ({actor})"
        notify(session, "access_rejected", f"{short}: {target.display}", f"Admin: {actor}", level="warning",
               audience="bot", link="/qr/requests")
    await session.commit()
    await cb.answer(short)
    if parts[1] == "ok":
        with suppress(Exception):
            await bot.send_message(target.telegram_id, t(settings, target, "approved"))
    if cb.message:
        with suppress(Exception):
            await cb.message.edit_text(f"{cb.message.text or ''}\n\n{result}", reply_markup=None)


async def set_commands(bot: Bot) -> None:
    """Buyruqlar menyusi: hamma uchun oddiy, adminlar chatida — admin buyruqlari ham."""
    with suppress(Exception):
        await bot.set_my_commands(BASE_COMMANDS)
    async with session_scope() as s:
        chats = await admins.chat_ids(s, await settings_store.load(s))
    for chat in chats:
        with suppress(Exception):
            await bot.set_my_commands(BASE_COMMANDS + ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=chat))


@on("message")
async def other(msg: Message, session, acc: TgAccount, created: bool, settings: dict[str, Any]):
    if not await gate(msg, session, acc, created, settings):
        return
    await msg.reply(t(settings, acc, "send_file"))


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
        self.bg: set[asyncio.Task] = set()

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
                self.bg.add(asyncio.create_task(set_commands(bot)))  # fonda — pollingni kechiktirmaydi
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
