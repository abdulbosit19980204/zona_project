"""Xodimlar va Telegram akkauntlar: username o'zgarishi, kirish so'rovlari, taklif havolalari.
Papka xodimga bog'langan — akkaunt o'zgarsa ham papka va fayllar saqlanadi."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import token
from ..db.models import Employee, Invite, TgAccount, TgAccountHistory
from .audit import add_audit, notify
from .naming import slug

INVITE_HOURS = 24


async def _accounts_of(session: AsyncSession, emp_id: int) -> list[TgAccount]:
    return list((await session.execute(select(TgAccount).where(TgAccount.employee_id == emp_id))).scalars())


TELEGRAM_FIELDS = ("id", "is_bot", "first_name", "last_name", "username", "language_code", "is_premium",
                   "added_to_attachment_menu", "can_join_groups", "can_read_all_group_messages", "supports_inline_queries")


async def touch(session: AsyncSession, user: dict[str, Any], registration: bool = False) -> tuple[TgAccount, bool]:
    """Har bir xabarda: akkauntni topadi yoki yaratadi, Telegram ma'lumotlarini to'liq saqlaydi,
    username/ism o'zgarsa tarixga yozadi. registration=True — yangi foydalanuvchi avval ro'yxatdan o'tadi.
    Qaytaradi: (akkaunt, yangi_yaratildimi)."""
    tid = int(user["id"])
    acc = (await session.execute(select(TgAccount).where(TgAccount.telegram_id == tid))).scalar_one_or_none()
    username = (user.get("username") or "").strip()
    first, last = (user.get("first_name") or "").strip(), (user.get("last_name") or "").strip()
    now = datetime.now(timezone.utc)
    if acc is None:
        lang = "ru" if (user.get("language_code") or "").startswith("ru") else "uz"
        acc = TgAccount(telegram_id=tid, username=username, first_name=first, last_name=last, lang=lang,
                        status="registering" if registration else "pending", first_seen=now, last_seen=now,
                        reg_state="name" if registration else "", reg_data={}, profile={})
        _store_telegram(acc, user)
        session.add(acc)
        await session.flush()
        return acc, True
    _store_telegram(acc, user)
    for field, new in (("username", username), ("first_name", first), ("last_name", last)):
        old = getattr(acc, field) or ""
        if old != new:
            session.add(TgAccountHistory(account_id=acc.id, field=field, old=old, new=new))
            setattr(acc, field, new)
            if field == "username":
                add_audit(session, "tg.username_changed", actor=str(tid), actor_kind="bot",
                          target=acc.display, details={"old": old, "new": new})
    acc.last_seen = now
    return acc, False


def _store_telegram(acc: TgAccount, user: dict[str, Any]) -> None:
    profile = dict(acc.profile or {})
    # birlashtiriladi: ba'zi update turlarida (callback va h.k.) maydonlar kelmasligi mumkin
    tg = {**(profile.get("telegram") or {}), **{k: user.get(k) for k in TELEGRAM_FIELDS if user.get(k) is not None}}
    tg["is_premium"] = bool(user.get("is_premium"))
    acc.is_premium = tg["is_premium"]
    if profile.get("telegram") != tg:
        profile["telegram"] = tg
        acc.profile = profile


async def access_state(session: AsyncSession, acc: TgAccount) -> str:
    """ok | registering | pending | blocked"""
    if acc.status == "registering":
        return "registering"
    emp = await session.get(Employee, acc.employee_id) if acc.employee_id else None
    if acc.status == "active" and emp and emp.status == "active":
        return "ok"
    if acc.status == "pending":
        return "pending"
    return "blocked"


def describe(acc: TgAccount) -> str:
    """Admin uchun foydalanuvchi haqida to'liq ma'lumot (bildirishnoma matni)."""
    reg = acc.reg_data or {}
    tg = (acc.profile or {}).get("telegram") or {}
    lines = [f"👤 {reg.get('full_name') or acc.display}",
             f"🆔 {acc.telegram_id}" + (f" · @{acc.username}" if acc.username else "")]
    tg_name = f"{acc.first_name} {acc.last_name}".strip()
    if tg_name and tg_name != reg.get("full_name"):
        lines.append(f"Telegram ismi: {tg_name}")
    if acc.phone:
        lines.append(f"📱 {acc.phone}")
    if reg.get("department"):
        lines.append(f"🏢 {reg['department']}")
    if reg.get("position"):
        lines.append(f"💼 {reg['position']}")
    extra = [x for x in (f"til: {tg['language_code']}" if tg.get("language_code") else "", "⭐ Premium" if acc.is_premium else "") if x]
    if extra:
        lines.append(" · ".join(extra))
    bio = ((acc.profile or {}).get("chat") or {}).get("bio")
    if bio:
        lines.append(f"Bio: {bio}")
    return "\n".join(lines)


def request_notification(session: AsyncSession, acc: TgAccount) -> None:
    reg = acc.reg_data or {}
    who = reg.get("full_name") or acc.display
    notify(session, "access_request", f"Yangi kirish so'rovi: {who}", describe(acc), level="info", link="/qr/requests",
           data={"account_id": acc.id})


def employee_folder(emp: Employee, acc: TgAccount | None) -> str:
    """Papka nomi: belgilangan bo'lsa — o'shani; bo'lmasa username'dan (eski bot qoidasi), keyin F.I.Sh."""
    if emp.folder:
        return emp.folder
    if acc and acc.username:
        return slug(acc.username)
    if acc:
        return slug(f"{acc.first_name or 'user'}_{acc.telegram_id}")
    return slug(emp.full_name)


async def unique_folder(session: AsyncSession, base: str, exclude_id: int | None = None) -> str:
    base = slug(base)
    existing = {f.lower() for f in (await session.execute(
        select(Employee.folder).where(Employee.id != (exclude_id or 0)))).scalars() if f}
    name, n = base, 2
    while name.lower() in existing:
        name, n = f"{base}_{n}", n + 1
    return name


async def create_invite(session: AsyncSession, emp: Employee, actor: str, replace: bool = True) -> Invite:
    inv = Invite(code=token(12), employee_id=emp.id, replace=replace,
                 expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITE_HOURS))
    session.add(inv)
    add_audit(session, "employee.invite", actor=actor, target=emp.full_name)
    await session.flush()
    return inv


async def redeem_invite(session: AsyncSession, acc: TgAccount, code: str) -> Employee | None:
    inv = (await session.execute(select(Invite).where(Invite.code == code))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if inv is None or inv.used_at is not None or inv.expires_at < now:
        return None
    emp = await session.get(Employee, inv.employee_id)
    if emp is None or emp.status == "archived":
        return None
    if inv.replace:
        for other in await _accounts_of(session, emp.id):
            if other.id != acc.id and other.status == "active":
                other.status = "detached"
                session.add(TgAccountHistory(account_id=other.id, field="status", old="active", new="detached"))
    previous = acc.employee_id
    acc.employee_id, acc.status = emp.id, "active"
    if not emp.folder:  # papka nomi shu paytdan qotiriladi
        emp.folder = await unique_folder(session, employee_folder(emp, acc), emp.id)
    inv.used_at, inv.used_by = now, acc.telegram_id
    session.add(TgAccountHistory(account_id=acc.id, field="employee", old=str(previous or ""), new=str(emp.id)))
    add_audit(session, "tg.invite_redeemed", actor=str(acc.telegram_id), actor_kind="bot", target=emp.full_name)
    await session.flush()
    await session.refresh(emp, ["accounts"])
    return emp


async def approve_as_new(session: AsyncSession, acc: TgAccount, actor: str, data: dict[str, Any]) -> Employee:
    reg = acc.reg_data or {}  # botdagi ro'yxatdan o'tish ma'lumotlari — admin o'zgartirmasa shular olinadi
    full_name = (data.get("full_name") or "").strip() or reg.get("full_name") or acc.display
    emp = Employee(full_name=full_name, department=data.get("department") or reg.get("department") or "",
                   position=data.get("position") or reg.get("position") or "", phone=data.get("phone") or acc.phone or "")
    session.add(emp)
    await session.flush()
    emp.folder = await unique_folder(session, data.get("folder") or employee_folder(emp, acc), emp.id)
    acc.employee_id, acc.status = emp.id, "active"
    add_audit(session, "request.approved", actor=actor, target=acc.display, details={"employee": emp.full_name})
    return emp


async def attach_existing(session: AsyncSession, acc: TgAccount, emp: Employee, actor: str, replace: bool = False) -> None:
    if replace:
        for other in await _accounts_of(session, emp.id):
            if other.id != acc.id and other.status == "active":
                other.status = "detached"
    acc.employee_id, acc.status = emp.id, "active"
    if not emp.folder:
        emp.folder = await unique_folder(session, employee_folder(emp, acc), emp.id)
    add_audit(session, "request.attached", actor=actor, target=acc.display, details={"employee": emp.full_name})
