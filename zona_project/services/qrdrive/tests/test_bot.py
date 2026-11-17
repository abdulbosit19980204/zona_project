"""Bot handlerlari: haqiqiy aiogram Dispatcher, Telegram esa soxta sessiya (tarmoqsiz)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User
from sqlalchemy import select

from qrdrive.bot.main import BotService
from qrdrive.db.models import FileRecord, Notification, TgAccount
from qrdrive.db.session import session_scope
from qrdrive.services import accounts

TOKEN = "123456:" + "A" * 35


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.next_id = 100

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        data = method.model_dump(exclude_none=True)
        self.sent.append((type(method).__name__, data))
        self.next_id += 1
        if type(method).__name__ in ("SendMessage", "SendPhoto"):
            return Message(message_id=self.next_id, date=datetime.now(timezone.utc),
                           chat=Chat(id=data["chat_id"], type="private"), text=data.get("text", ""))
        return True

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self) -> None:
        return None

    def texts(self) -> list[str]:
        return [d.get("text", "") for name, d in self.sent if name == "SendMessage"]


_uid = 0


def update(user_id: int, username: str = "", text: str | None = None, document: dict | None = None) -> Update:
    global _uid
    _uid += 1
    msg: dict[str, Any] = {"message_id": _uid, "date": int(datetime.now().timestamp()),
                           "chat": {"id": user_id, "type": "private"},
                           "from": {"id": user_id, "is_bot": False, "first_name": "Ali", "username": username or None}}
    if text is not None:
        msg["text"] = text
        if text.startswith("/"):
            msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    if document:
        msg["document"] = document
    return Update.model_validate({"update_id": _uid, "message": msg})


async def feed(service: BotService, upd: Update) -> FakeSession:
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    await service.dp.feed_update(bot, upd)
    return session


async def test_unknown_user_gets_request(session):
    service = BotService()
    s = await feed(service, update(501, "yangi", "/start"))
    assert "administratorga yuborildi" in s.texts()[0]
    s = await feed(service, update(501, "yangi", "salom"))
    assert "ko'rib chiqilmoqda" in s.texts()[0]
    async with session_scope() as db:
        acc = (await db.execute(select(TgAccount).where(TgAccount.telegram_id == 501))).scalar_one()
        assert acc.status == "pending"
        kinds = [n.kind for n in (await db.execute(select(Notification))).scalars()]
        assert kinds == ["access_request"]


async def test_invite_then_file_upload(session, employee, local_storage):
    inv = await accounts.create_invite(session, employee, "admin")
    await session.commit()
    service = BotService()
    s = await feed(service, update(600, "dilnoza_tg", f"/start {inv.code}"))
    assert "Olimova Dilnoza" in s.texts()[0]
    s = await feed(service, update(600, "dilnoza_tg", document={"file_id": "FID1", "file_unique_id": "U1",
                                                                "file_name": "Buyruq.pdf", "file_size": 2048}))
    assert s.sent[0][0] == "SendMessage" and "qabul qilindi" in s.texts()[0]
    async with session_scope() as db:
        rec = (await db.execute(select(FileRecord))).scalar_one()
        assert rec.source == "telegram" and rec.employee_id == employee.id and rec.tg_file_id == "FID1"
        assert rec.status == "queued" and rec.tg_status_msg_id


async def test_too_big_rejected_in_bot(session, employee):
    acc, _ = await accounts.touch(session, {"id": 700, "username": "a"})
    acc.employee_id, acc.status = employee.id, "active"
    await session.commit()
    s = await feed(BotService(), update(700, "a", document={"file_id": "F", "file_unique_id": "U", "file_name": "big.zip",
                                                            "file_size": 500 * 1024 * 1024}))
    assert "juda katta" in s.texts()[0]
    async with session_scope() as db:
        assert (await db.execute(select(FileRecord))).first() is None


async def test_id_and_username_change(session, employee):
    acc, _ = await accounts.touch(session, {"id": 800, "username": "eski"})
    acc.employee_id, acc.status = employee.id, "active"
    await session.commit()
    s = await feed(BotService(), update(800, "yangi", "/id"))
    assert "800" in s.texts()[0]
    async with session_scope() as db:
        acc = (await db.execute(select(TgAccount).where(TgAccount.telegram_id == 800))).scalar_one()
        assert acc.username == "yangi" and acc.employee_id == employee.id
