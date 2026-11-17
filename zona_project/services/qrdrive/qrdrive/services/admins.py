"""Bot adminlari: sozlamadagi @username yoki Telegram ID ro'yxati.
Adminlar botda hamma bildirishnomani oladi, kirish so'rovlarini tugma bilan tasdiqlaydi va /stats, /pending buyruqlaridan foydalanadi.
Admin botga kamida bir marta /start bosgan bo'lishi kerak — Telegram botga avval yozmagan odamga xabar yuborishga ruxsat bermaydi."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Employee, FileRecord, Storage, TgAccount
from .audit import add_audit, notify

MODES = ("manual", "auto")


def parse(value: str) -> tuple[set[int], set[str]]:
    """«@ali, 12345, vali» -> ({12345}, {"ali", "vali"})"""
    ids: set[int] = set()
    names: set[str] = set()
    for part in re.split(r"[,;\s]+", value or ""):
        part = part.strip()
        if not part:
            continue
        if part.lstrip("-").isdigit():
            ids.add(int(part))
        else:
            names.add(part.lstrip("@").lower())
    return ids, names


def is_admin(acc: TgAccount | None, settings: dict[str, Any]) -> bool:
    if acc is None:
        return False
    ids, names = parse(settings.get("bot_admins") or "")
    return acc.telegram_id in ids or bool(acc.username and acc.username.lower() in names)


async def chat_ids(session: AsyncSession, settings: dict[str, Any]) -> list[int]:
    """Adminlarning Telegram ID'lari (username bo'yicha — botga yozgan akkauntlardan topiladi)."""
    ids, names = parse(settings.get("bot_admins") or "")
    out = set(ids)
    if names:
        rows = await session.execute(select(TgAccount.telegram_id).where(func.lower(TgAccount.username).in_(names)))
        out.update(int(r) for r in rows.scalars())
    return sorted(out)


async def ensure_admin_access(session: AsyncSession, acc: TgAccount, settings: dict[str, Any]) -> bool:
    """Admin ro'yxatdan o'tish va tasdiqlashni kutmaydi: akkaunt darhol faollashadi. True — o'zgartirildi."""
    if not is_admin(acc, settings) or acc.status not in ("registering", "pending"):
        return False
    from .accounts import approve_as_new
    acc.reg_state = ""
    await approve_as_new(session, acc, "bot_admin", {})
    return True


async def auto_approve(session: AsyncSession, acc: TgAccount, settings: dict[str, Any]) -> bool:
    """«auto» rejimda yangi so'rov darhol tasdiqlanadi (adminlarga xabar boradi). True — tasdiqlandi."""
    if (settings.get("approval_mode") or "manual") != "auto" or acc.status != "pending":
        return False
    from .accounts import approve_as_new, describe
    emp = await approve_as_new(session, acc, "auto", {})
    add_audit(session, "request.auto_approved", actor="auto", actor_kind="system", target=acc.display,
              details={"employee": emp.full_name})
    notify(session, "access_auto", f"Avtomatik tasdiqlandi: {emp.full_name}", describe(acc), level="success",
           link="/qr/employees", data={"account_id": acc.id})
    return True


async def stats_text(session: AsyncSession) -> str:
    """/stats — qisqa holat: bugungi fayllar, navbat, xatolar, so'rovlar, saqlash joylari."""
    now = datetime.now(timezone.utc)
    day = now - timedelta(hours=24)

    async def count(*where) -> int:
        return (await session.execute(select(func.count()).select_from(FileRecord).where(*where))).scalar_one()

    ok = await count(FileRecord.status == "delivered", FileRecord.finished_at >= day)
    bad = await count(FileRecord.status == "failed", FileRecord.finished_at >= day)
    queue = await count(FileRecord.status.in_(("queued", "processing", "retrying", "awaiting")))
    failed = await count(FileRecord.status == "failed", FileRecord.deleted_at.is_(None))
    total = await count(FileRecord.status == "delivered", FileRecord.deleted_at.is_(None))
    pending = (await session.execute(select(func.count()).select_from(TgAccount).where(TgAccount.status == "pending"))).scalar_one()
    emps = (await session.execute(select(func.count()).select_from(Employee).where(Employee.status == "active"))).scalar_one()
    lines = ["📊 QR Drive holati",
             f"Oxirgi 24 soat: ✅ {ok} ta saqlandi, ❌ {bad} ta xato",
             f"Navbatda: {queue} · Hal qilinmagan xatolar: {failed}",
             f"Jami fayllar: {total} · Faol xodimlar: {emps}",
             f"Kutilayotgan so'rovlar: {pending}", "", "💾 Saqlash joylari:"]
    for st in (await session.execute(select(Storage).where(Storage.enabled.is_(True)).order_by(Storage.id))).scalars():
        icon = {"ok": "🟢", "down": "🔴"}.get(st.status or "", "⚪")
        lines.append(f"{icon} {st.name}" + (" (asosiy)" if st.is_primary else ""))
    return "\n".join(lines)
