"""Bot handlerlari: haqiqiy aiogram Dispatcher, Telegram esa soxta sessiya (tarmoqsiz)."""
from __future__ import annotations

import asyncio

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User
from sqlalchemy import select

from qrdrive.bot.main import Batcher, BotService, batcher
from qrdrive.db.models import FileRecord, Notification, TgAccount
from qrdrive.db.session import session_scope
from qrdrive.services import accounts

TOKEN = "123456:" + "A" * 35
Batcher.WINDOW = 0.05


async def settle() -> None:
    """Guruh oynasi yopilishini kutish (bot savolni guruh yopilgach beradi)."""
    for _ in range(40):
        await asyncio.sleep(0.05)
        if not batcher.pending and not batcher.tasks:
            return


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
                           chat=Chat(id=data["chat_id"], type="private"), text=data.get("text", "")).as_(bot)
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


def contact_update(user_id: int, phone: str, owner: int | None = None) -> Update:
    global _uid
    _uid += 1
    return Update.model_validate({"update_id": _uid, "message": {
        "message_id": _uid, "date": int(datetime.now().timestamp()), "chat": {"id": user_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Ali", "language_code": "uz", "is_premium": True},
        "contact": {"phone_number": phone, "first_name": "Ali", "user_id": owner if owner is not None else user_id}}})


def callback(user_id: int, data: str) -> Update:
    global _uid
    _uid += 1
    return Update.model_validate({"update_id": _uid, "callback_query": {
        "id": f"cb{_uid}", "chat_instance": "x", "data": data,
        "from": {"id": user_id, "is_bot": False, "first_name": "Ali"},
        "message": {"message_id": 7, "date": 0, "chat": {"id": user_id, "type": "private"}, "text": "?"}}})


async def test_registration_required_before_request(session):
    from qrdrive.db.models import Employee
    session.add(Employee(full_name="Bor xodim", department="Kadrlar"))
    await session.commit()
    service = BotService()
    s = await feed(service, update(501, "yangi", "/start"))
    assert "ro'yxatdan o'ting" in s.texts()[0] and "F.I.Sh." in s.texts()[1]
    async with session_scope() as db:
        acc = (await db.execute(select(TgAccount).where(TgAccount.telegram_id == 501))).scalar_one()
        assert acc.status == "registering" and acc.reg_state == "name"
        assert (await db.execute(select(Notification))).first() is None  # hali so'rov yo'q
    s = await feed(service, update(501, "yangi", document={"file_id": "F", "file_unique_id": "U", "file_name": "a.pdf"}))
    assert "Avval ro'yxatdan o'ting" in s.texts()[0]  # fayl qabul qilinmaydi
    s = await feed(service, update(501, "yangi", "Ali"))  # bitta so'z — rad
    assert "kamida 2 so'z" in s.texts()[0]
    s = await feed(service, update(501, "yangi", "Aliyev Ali Valiyevich"))
    assert "Telefon" in s.texts()[0]
    s = await feed(service, update(501, "yangi", document={"file_id": "F", "file_unique_id": "U", "file_name": "a.pdf"}))
    assert "o'z raqamingizni" in s.texts()[0]  # telefon qadamida ham fayl qabul qilinmaydi
    s = await feed(service, contact_update(501, "998901234567", owner=777))  # boshqa odamning raqami
    assert "o'z raqamingizni" in s.texts()[0]
    s = await feed(service, contact_update(501, "998901234567"))
    assert "Bo'limingizni" in s.texts()[0]
    kb = next(d for n, d in s.sent if n == "SendMessage" and "Bo'limingizni" in d["text"])["reply_markup"]["keyboard"]
    assert kb[0][0]["text"] == "Kadrlar"  # mavjud bo'limlar tugma sifatida
    await feed(service, update(501, "yangi", "Kadrlar"))
    s = await feed(service, update(501, "yangi", "⏭ O'tkazib yuborish"))
    summary = next(d for n, d in s.sent if n == "SendMessage" and "To'g'rimi" in d.get("text", ""))
    assert "Aliyev Ali Valiyevich" in summary["text"] and "+998901234567" in summary["text"] and "Kadrlar" in summary["text"]
    s = await feed(service, callback(501, "reg:ok"))
    assert any(n == "EditMessageText" and "Ro'yxatdan o'tdingiz" in d["text"] for n, d in s.sent)
    async with session_scope() as db:
        acc = (await db.execute(select(TgAccount).where(TgAccount.telegram_id == 501))).scalar_one()
        assert acc.status == "pending" and acc.phone == "+998901234567" and acc.registered_at
        assert acc.reg_data == {"full_name": "Aliyev Ali Valiyevich", "department": "Kadrlar", "position": ""}
        assert acc.profile["telegram"]["id"] == 501 and acc.profile["telegram"]["username"] == "yangi"
        n = (await db.execute(select(Notification))).scalar_one()
        assert n.kind == "access_request" and "Aliyev Ali Valiyevich" in n.title and "+998901234567" in n.body
    s = await feed(service, update(501, "yangi", "salom"))
    assert "ko'rib chiqilmoqda" in s.texts()[0]


async def test_registration_restart(session):
    service = BotService()
    await feed(service, update(502, "b", "/start"))
    await feed(service, update(502, "b", "Karimov Bobur"))
    await feed(service, contact_update(502, "+998 90 111 22 33"))
    await feed(service, update(502, "b", "IT"))
    await feed(service, update(502, "b", "Dasturchi"))
    await feed(service, callback(502, "reg:edit"))
    async with session_scope() as db:
        acc = (await db.execute(select(TgAccount).where(TgAccount.telegram_id == 502))).scalar_one()
        assert acc.status == "registering" and acc.reg_state == "name" and acc.reg_data == {}


async def test_approve_uses_registration_data(client, session):
    from qrdrive.db.models import Employee
    from .conftest import auth
    acc = TgAccount(telegram_id=900, first_name="X", status="pending", phone="+998900000000",
                    reg_data={"full_name": "Olimov Olim", "department": "Moliya", "position": "Hisobchi"})
    session.add(acc)
    await session.commit()
    rows = (await client.get("/qrdrive/api/admin/requests", headers=auth("viewer"))).json()
    assert rows[0]["reg"]["full_name"] == "Olimov Olim" and rows[0]["phone"] == "+998900000000"
    r = await client.post(f"/qrdrive/api/admin/requests/{acc.id}/approve", headers=auth("admin"), json={})
    async with session_scope() as db:
        emp = await db.get(Employee, r.json()["employee_id"])
        assert (emp.full_name, emp.department, emp.position, emp.phone) == ("Olimov Olim", "Moliya", "Hisobchi", "+998900000000")


async def test_invite_then_file_upload(session, employee, local_storage):
    inv = await accounts.create_invite(session, employee, "admin")
    await session.commit()
    service = BotService()
    s = await feed(service, update(600, "dilnoza_tg", f"/start {inv.code}"))
    assert "Olimova Dilnoza" in s.texts()[0]
    s = await feed(service, update(600, "dilnoza_tg", document={"file_id": "FID1", "file_unique_id": "U1",
                                                                "file_name": "Buyruq.pdf", "file_size": 2048}))
    assert s.sent[0][0] == "SendChatAction"  # darhol «yuklanmoqda…» belgisi
    await settle()
    assert "Havola turini tanlang" in s.texts()[0] and "Buyruq.pdf" in s.texts()[0]
    kb = next(d for n, d in s.sent if n == "SendMessage")["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"].split(":")[-1] for b in kb] == ["public", "private"]
    async with session_scope() as db:
        rec = (await db.execute(select(FileRecord))).scalar_one()
        assert rec.source == "telegram" and rec.employee_id == employee.id and rec.tg_file_id == "FID1"
        assert rec.status == "awaiting" and rec.tg_status_msg_id
    # foydalanuvchi «Private» ni bosdi
    raw = {"update_id": 9999, "callback_query": {
        "id": "cb1", "chat_instance": "x", "data": kb[1]["callback_data"],
        "from": {"id": 600, "is_bot": False, "first_name": "Ali", "username": "dilnoza_tg"},
        "message": {"message_id": 5, "date": 0, "chat": {"id": 600, "type": "private"}, "text": "?"}}}
    s = await feed(service, Update.model_validate(raw))
    assert any(n == "EditMessageText" and "Private" in d["text"] for n, d in s.sent)
    async with session_scope() as db:
        rec = (await db.execute(select(FileRecord))).scalar_one()
        assert rec.status == "queued" and rec.options["visibility"] == "private"
    raw["update_id"] = 10000
    raw["callback_query"]["data"] = kb[0]["callback_data"]  # keyin «Public» bosilsa — o'zgarmaydi
    await feed(service, Update.model_validate(raw))
    async with session_scope() as db:
        assert (await db.execute(select(FileRecord))).scalar_one().options["visibility"] == "private"


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


async def test_many_files_one_question(session, employee, local_storage):
    acc = TgAccount(telegram_id=650, employee_id=employee.id, status="active")
    session.add(acc)
    await session.commit()
    service = BotService()
    sessions = [await feed(service, update(650, "x", document={"file_id": f"F{i}", "file_unique_id": f"U{i}",
                                                                 "file_name": f"hujjat{i}.pdf", "file_size": 100}))
                for i in range(3)]
    await settle()
    msgs = [d for s in sessions for n, d in s.sent if n == "SendMessage"]
    assert len(msgs) == 1 and "3 ta fayl" in msgs[0]["text"]  # bitta savol, uchta emas
    rows = msgs[0]["reply_markup"]["inline_keyboard"]
    assert [b["callback_data"].split(":")[2] for b in rows[0]] == ["folder", "folder"]
    assert [b["callback_data"].split(":")[2] for b in rows[1]] == ["separate", "separate"]
    raw = {"update_id": 7777, "callback_query": {"id": "c", "chat_instance": "x", "data": rows[0][0]["callback_data"],
           "from": {"id": 650, "is_bot": False, "first_name": "A"},
           "message": {"message_id": 9, "date": 0, "chat": {"id": 650, "type": "private"}, "text": "?"}}}
    await feed(service, Update.model_validate(raw))
    async with session_scope() as db:
        recs = (await db.execute(select(FileRecord).order_by(FileRecord.id))).scalars().all()
        folder = recs[-1]
        assert [r.status for r in recs[:3]] == ["merged"] * 3
        assert folder.status == "queued" and folder.options["batch_children"] == [r.id for r in recs[:3]]
        assert folder.options["visibility"] == "public" and folder.tg_status_msg_id == 9
