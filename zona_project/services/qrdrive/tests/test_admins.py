"""Bot adminlari (to'liq bildirishnomalar, botda tasdiqlash) va tasdiqlash rejimi (auto / manual)."""
from __future__ import annotations

from typing import Any

from aiogram.types import Update
from sqlalchemy import select

from qrdrive import settings_store
from qrdrive.bot.main import BotService
from qrdrive.db.models import Employee, Notification, TgAccount
from qrdrive.db.session import session_scope
from qrdrive.services import admins
from qrdrive.services.audit import notify
from qrdrive.worker import main as worker_main

from .conftest import auth
from .test_bot import feed, update

ADMIN_ID = 1209619850
_n = 0


def cb(user_id: int, data: str, username: str = "") -> Update:
    global _n
    _n += 1
    return Update.model_validate({"update_id": 90000 + _n, "callback_query": {
        "id": f"a{_n}", "chat_instance": "x", "data": data,
        "from": {"id": user_id, "is_bot": False, "first_name": "Admin", "username": username or None},
        "message": {"message_id": 7, "date": 0, "chat": {"id": user_id, "type": "private"}, "text": "Yangi kirish so'rovi"}}})


def test_parse_admins():
    assert admins.parse("@Ali, 123 ;vali  -100") == ({123, -100}, {"ali", "vali"})
    acc = TgAccount(telegram_id=5, username="ABDULBOSIT_TATU")
    assert admins.is_admin(acc, {"bot_admins": "@abdulbosit_tatu"})  # katta-kichik harf farqi yo'q
    assert not admins.is_admin(acc, {"bot_admins": "@boshqa"})
    assert admins.is_admin(acc, {"bot_admins": "5"})


async def test_admin_is_active_immediately(session):
    """Standart admin (@abdulbosit_tatu) ro'yxatdan o'tish/tasdiqlashni kutmaydi va admin buyruqlarini ko'radi."""
    service = BotService()
    s = await feed(service, update(ADMIN_ID, "abdulbosit_tatu", "/start"))
    assert "Admin buyruqlari" in s.texts()[-1]
    assert any(n == "SetMyCommands" for n, _ in s.sent)
    async with session_scope() as db:
        acc = (await db.execute(select(TgAccount).where(TgAccount.telegram_id == ADMIN_ID))).scalar_one()
        assert acc.status == "active" and acc.employee_id
    s = await feed(service, update(ADMIN_ID, "abdulbosit_tatu", "/stats"))
    assert "QR Drive holati" in s.texts()[0]


async def test_non_admin_cannot_use_admin_commands(session, employee):
    session.add(TgAccount(telegram_id=40, username="oddiy", employee_id=employee.id, status="active"))
    pending = TgAccount(telegram_id=41, username="kutuvchi", status="pending")
    session.add(pending)
    await session.commit()
    service = BotService()
    s = await feed(service, update(40, "oddiy", "/stats"))
    assert "QR Drive holati" not in "".join(s.texts())
    await feed(service, cb(40, f"adm:ok:{pending.id}", "oddiy"))
    async with session_scope() as db:
        assert (await db.get(TgAccount, pending.id)).status == "pending"  # oddiy foydalanuvchi tasdiqlay olmaydi


async def test_admin_approves_and_rejects_in_bot(session):
    a = TgAccount(telegram_id=51, username="yangi1", first_name="Vali", status="pending", phone="+998901112233",
                  reg_data={"full_name": "Valiyev Vali", "department": "IT", "position": "Dasturchi"})
    b = TgAccount(telegram_id=52, username="yangi2", status="pending")
    session.add_all([a, b])
    await session.commit()
    service = BotService()
    await feed(service, update(ADMIN_ID, "abdulbosit_tatu", "/start"))
    s = await feed(service, update(ADMIN_ID, "abdulbosit_tatu", "/pending"))
    msgs = [d for n, d in s.sent if n == "SendMessage"]
    assert "Kutilayotgan so'rovlar: 2" in msgs[0]["text"]
    card = next(d for d in msgs if "Valiyev Vali" in d["text"])
    assert "+998901112233" in card["text"] and "IT" in card["text"] and "Dasturchi" in card["text"]
    assert card["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"adm:ok:{a.id}"

    s = await feed(service, cb(ADMIN_ID, f"adm:ok:{a.id}", "abdulbosit_tatu"))
    told = [d for n, d in s.sent if n == "SendMessage"]
    assert told and told[0]["chat_id"] == 51 and "tasdiqlandi" in told[0]["text"]
    edit = next(d for n, d in s.sent if n == "EditMessageText")
    assert "Tasdiqlandi (@abdulbosit_tatu)" in edit["text"]
    s = await feed(service, cb(ADMIN_ID, f"adm:ok:{a.id}", "abdulbosit_tatu"))  # ikkinchi marta — allaqachon
    assert any(n == "AnswerCallbackQuery" and "allaqachon" in d.get("text", "") for n, d in s.sent)
    await feed(service, cb(ADMIN_ID, f"adm:no:{b.id}", "abdulbosit_tatu"))
    async with session_scope() as db:
        acc_a, acc_b = await db.get(TgAccount, a.id), await db.get(TgAccount, b.id)
        assert acc_a.status == "active" and acc_b.status == "rejected"
        emp = await db.get(Employee, acc_a.employee_id)
        assert (emp.full_name, emp.department) == ("Valiyev Vali", "IT")
        kinds = [n.kind for n in (await db.execute(select(Notification))).scalars()]
        assert "access_approved" in kinds and "access_rejected" in kinds


async def test_auto_approval_mode(session):
    await settings_store.save(session, {"approval_mode": "auto"})
    acc = TgAccount(telegram_id=61, username="avto", status="registering", reg_state="confirm",
                    reg_data={"full_name": "Avtomat Ali", "department": "", "position": ""})
    session.add(acc)
    await session.commit()
    service = BotService()
    s = await feed(service, cb(61, "reg:ok", "avto"))
    assert any(n == "EditMessageText" and "tasdiqlandi" in d["text"] for n, d in s.sent)
    async with session_scope() as db:
        got = await db.get(TgAccount, acc.id)
        assert got.status == "active" and got.employee_id
        kinds = [n.kind for n in (await db.execute(select(Notification))).scalars()]
        assert kinds == ["access_auto"]  # so'rov emas — adminga «avtomatik tasdiqlandi» xabari


async def test_mode_switch_from_bot(session):
    service = BotService()
    await feed(service, update(ADMIN_ID, "abdulbosit_tatu", "/start"))
    s = await feed(service, update(ADMIN_ID, "abdulbosit_tatu", "/mode"))
    assert "Qo'lda" in s.texts()[0]
    await feed(service, cb(ADMIN_ID, "mode:auto", "abdulbosit_tatu"))
    async with session_scope() as db:
        assert (await settings_store.load(db, fresh=True))["approval_mode"] == "auto"


async def test_worker_sends_everything_to_admins(session, monkeypatch):
    await settings_store.save(session, {"bot_token": "123:abc", "notify_chat_ids": "-100500"})
    session.add(TgAccount(telegram_id=ADMIN_ID, username="abdulbosit_tatu", status="active"))
    req = TgAccount(telegram_id=71, username="soruvchi", status="pending")
    session.add(req)
    await session.flush()
    notify(session, "access_request", "Yangi kirish so'rovi: X", "tafsilot", data={"account_id": req.id})
    notify(session, "file_delivered", "📄 Yangi fayl: a.pdf", "havola", audience="bot")
    await session.commit()
    sent: list[tuple[int, str, Any]] = []

    class FakeTg:
        @classmethod
        def from_settings(cls, _s):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def send_message(self, chat, text, reply_markup=None):
            sent.append((chat, text, reply_markup))

    monkeypatch.setattr(worker_main, "TelegramClient", FakeTg)
    await worker_main.Worker().notifications()
    to_admin = [x for x in sent if x[0] == ADMIN_ID]
    to_group = [x for x in sent if x[0] == -100500]
    assert len(to_admin) == 2 and to_admin[0][2]["inline_keyboard"][0][0]["callback_data"] == f"adm:ok:{req.id}"
    assert len(to_group) == 1 and to_group[0][2] is None  # kuzatuv chati: faylma-fayl xabar emas, tugmasiz


async def test_panel_hides_bot_only_and_validates_settings(client, session):
    notify(session, "file_delivered", "📄 Yangi fayl", audience="bot")
    notify(session, "file_failed", "Xato", level="error")
    await session.commit()
    data = (await client.get("/qrdrive/api/admin/notifications", headers=auth("viewer"))).json()
    assert [i["kind"] for i in data["items"]] == ["file_failed"] and data["unread"] == 1
    r = await client.patch("/qrdrive/api/admin/settings", headers=auth("admin"), json={"approval_mode": "x"})
    assert r.status_code == 400
    r = await client.patch("/qrdrive/api/admin/settings", headers=auth("admin"),
                           json={"approval_mode": "auto", "bot_admins": "abdulbosit_tatu 123, @Vali"})
    assert r.json()["approval_mode"] == "auto" and r.json()["bot_admins"] == "@abdulbosit_tatu, @vali, 123"
