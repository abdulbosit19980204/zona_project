"""Telegram: username o'zgarishi, akkaunt almashtirish (taklif kodi), ruxsatsiz foydalanuvchi, eski .env importi."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from qrdrive import settings_store
from qrdrive.db.models import Employee, Invite, Setting, Storage, TgAccount, TgAccountHistory
from qrdrive.services import accounts, system


async def test_unknown_user_is_pending(session):
    acc, created = await accounts.touch(session, {"id": 1, "username": "x", "first_name": "Ali"})
    assert created and acc.status == "pending"
    assert await accounts.access_state(session, acc) == "pending"


async def test_username_change_keeps_folder(session, employee):
    acc, _ = await accounts.touch(session, {"id": 5, "username": "old_name", "first_name": "Dilnoza"})
    acc.employee_id, acc.status = employee.id, "active"
    await session.commit()
    acc, created = await accounts.touch(session, {"id": 5, "username": "new_name", "first_name": "Dilnoza"})
    await session.commit()
    assert not created and acc.username == "new_name"
    hist = (await session.execute(select(TgAccountHistory).where(TgAccountHistory.account_id == acc.id))).scalars().all()
    assert [(h.field, h.old, h.new) for h in hist] == [("username", "old_name", "new_name")]
    assert (await session.get(Employee, employee.id)).folder == "dilnoza"
    assert await accounts.access_state(session, acc) == "ok"


async def test_invite_replaces_old_account(session, employee):
    old, _ = await accounts.touch(session, {"id": 10, "username": "eski"})
    old.employee_id, old.status = employee.id, "active"
    await session.commit()
    inv = await accounts.create_invite(session, employee, "admin")
    await session.commit()
    new, _ = await accounts.touch(session, {"id": 11, "username": "yangi"})
    emp = await accounts.redeem_invite(session, new, inv.code)
    await session.commit()
    assert emp and emp.id == employee.id
    assert new.status == "active" and new.employee_id == employee.id
    assert (await session.get(TgAccount, old.id)).status == "detached"
    assert await accounts.redeem_invite(session, new, inv.code) is None  # bir martalik


async def test_expired_invite(session, employee):
    inv = Invite(code="abc", employee_id=employee.id, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    session.add(inv)
    acc, _ = await accounts.touch(session, {"id": 12})
    await session.commit()
    assert await accounts.redeem_invite(session, acc, "abc") is None
    assert acc.status == "pending"


async def test_blocked_employee(session, employee):
    acc, _ = await accounts.touch(session, {"id": 13})
    acc.employee_id, acc.status = employee.id, "active"
    employee.status = "archived"
    await session.commit()
    assert await accounts.access_state(session, acc) == "blocked"


async def test_legacy_env_import(session):
    env = {"BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", "TELEGRAM_API_URL": "http://telegram-bot-api:8081",
           "MAX_FILE_MB": "150", "SYNO_URL": "https://nas:5001", "SYNO_USER": "qr", "SYNO_PASS": "p@ss",
           "SYNO_VERIFY_SSL": "false", "SYNO_BASE_FOLDER": "/Kadrlar", "ALLOWED_USER_IDS": "111, 222",
           "SHARE_EXPIRE_DAYS": "30"}
    assert await system.import_legacy(session, env)
    s = await settings_store.load(session, fresh=True)
    assert s["bot_token"] == env["BOT_TOKEN"] and s["max_file_mb"] == 150 and s["bot_api_local"] is True
    assert s["link_expire_days"] == 30
    row = await session.get(Setting, "bot_token")
    assert env["BOT_TOKEN"] not in (row.secret_enc or "") and row.value is None  # shifrlangan
    st = (await session.execute(select(Storage))).scalar_one()
    assert st.is_primary and st.base_folder == "/Kadrlar"
    from qrdrive.storage import registry
    assert registry.get_config(st)["password"] == "p@ss" and "p@ss" not in st.config_enc
    assert registry.public_config(st) == {"url": "https://nas:5001", "username": "qr", "password_set": True, "drive_folder": "", "verify_ssl": False}
    n = (await session.execute(select(func.count()).select_from(TgAccount).where(TgAccount.status == "active"))).scalar_one()
    assert n == 2
