"""Panel: xodimlar, Telegram akkauntlar, taklif havolalari, Excel/CSV import-eksport, kirish so'rovlari."""
from __future__ import annotations

import base64
import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import settings_store
from ...core.security import Principal
from ...db.models import Employee, FileRecord, Storage, TgAccount, TgAccountHistory
from ...db.session import get_session
from ...services import accounts, qr
from ...services.audit import add_audit
from ...services.files import serialize
from ...services.telegram import TelegramClient
from ..deps import admin, viewer

router = APIRouter(tags=["admin: employees"])


def account_out(a: TgAccount) -> dict[str, Any]:
    return {"id": a.id, "telegram_id": a.telegram_id, "username": a.username, "first_name": a.first_name,
            "last_name": a.last_name, "display": a.display, "lang": a.lang, "status": a.status,
            "employee_id": a.employee_id, "first_seen": a.first_seen, "last_seen": a.last_seen}


def employee_out(e: Employee, stats: tuple[int, int, Any] | None = None) -> dict[str, Any]:
    count, size, last = stats or (0, 0, None)
    return {"id": e.id, "full_name": e.full_name, "department": e.department, "position": e.position, "phone": e.phone,
            "folder": e.folder, "storage_id": e.storage_id, "status": e.status, "note": e.note, "created_at": e.created_at,
            "accounts": [account_out(a) for a in e.accounts if a.status != "detached"],
            "files_count": count, "files_size": size, "last_file_at": last}


async def _stats(session: AsyncSession) -> dict[int, tuple[int, int, Any]]:
    rows = (await session.execute(
        select(FileRecord.employee_id, func.count(), func.coalesce(func.sum(FileRecord.size), 0), func.max(FileRecord.created_at))
        .where(FileRecord.deleted_at.is_(None), FileRecord.status == "delivered").group_by(FileRecord.employee_id))).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows if r[0]}


@router.get("/employees")
async def list_employees(q: str = "", status: str = "", session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    query = select(Employee).order_by(Employee.full_name)
    if status:
        query = query.where(Employee.status.in_(status.split(",")))
    if q:
        like = f"%{q}%"
        query = query.where(Employee.full_name.ilike(like) | Employee.department.ilike(like) | Employee.phone.ilike(like)
                            | Employee.folder.ilike(like) | Employee.accounts.any(TgAccount.username.ilike(like)))
    stats = await _stats(session)
    return [employee_out(e, stats.get(e.id)) for e in (await session.execute(query)).scalars()]


class EmployeeIn(BaseModel):
    full_name: str | None = None
    department: str | None = None
    position: str | None = None
    phone: str | None = None
    folder: str | None = None
    storage_id: int | None = None
    note: str | None = None


@router.post("/employees")
async def create_employee(body: EmployeeIn, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    if not (body.full_name or "").strip():
        raise HTTPException(400, "F.I.Sh. kiriting")
    emp = Employee(full_name=body.full_name.strip(), department=(body.department or "").strip(),
                   position=(body.position or "").strip(), phone=(body.phone or "").strip(), note=body.note or "",
                   storage_id=body.storage_id)
    session.add(emp)
    await session.flush()
    emp.folder = await accounts.unique_folder(session, body.folder or emp.full_name, emp.id)
    add_audit(session, "employee.create", actor=user.username, target=emp.full_name)
    await session.commit()
    await session.refresh(emp, ["accounts"])
    return employee_out(emp)


async def _emp(session: AsyncSession, emp_id: int) -> Employee:
    emp = await session.get(Employee, emp_id)
    if emp is None:
        raise HTTPException(404, "Xodim topilmadi")
    return emp


@router.get("/employees/export.xlsx")
async def export_employees(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    wb = Workbook()
    ws = wb.active
    ws.title = "Xodimlar"
    ws.append(["F.I.Sh.", "Bo'lim", "Lavozim", "Telefon", "Papka", "Holat", "Telegram", "Fayllar soni"])
    stats = await _stats(session)
    for e in (await session.execute(select(Employee).order_by(Employee.full_name))).scalars():
        tg = ", ".join(f"@{a.username}" if a.username else str(a.telegram_id) for a in e.accounts if a.status == "active")
        ws.append([e.full_name, e.department, e.position, e.phone, e.folder, e.status, tg, stats.get(e.id, (0,))[0]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=qrdrive-xodimlar.xlsx"})


HEADERS = {"f.i.sh.": "full_name", "fish": "full_name", "f.i.sh": "full_name", "ism": "full_name", "full_name": "full_name",
           "фио": "full_name", "bo'lim": "department", "bolim": "department", "department": "department", "отдел": "department",
           "lavozim": "position", "position": "position", "должность": "position", "telefon": "phone", "phone": "phone",
           "телефон": "phone", "papka": "folder", "folder": "folder", "папка": "folder"}


def _rows_from_upload(name: str, data: bytes) -> list[dict[str, str]]:
    if name.lower().endswith((".xlsx", ".xlsm")):
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        rows = [[str(c).strip() if c is not None else "" for c in r] for r in ws.iter_rows(values_only=True)]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t") if text.strip() else csv.excel
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    if not rows:
        return []
    keys = [HEADERS.get(h.lower().replace("’", "'").replace("ʻ", "'"), "") for h in rows[0]]
    if "full_name" not in keys:  # sarlavhasiz fayl: 1-ustun F.I.Sh.
        keys = ["full_name", "department", "position", "phone", "folder"][: len(rows[0])]
    else:
        rows = rows[1:]
    return [{k: v for k, v in zip(keys, r) if k} for r in rows if any(r)]


@router.post("/employees/import")
async def import_employees(file: UploadFile = File(...), session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    try:
        rows = _rows_from_upload(file.filename or "", await file.read())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Faylni o'qib bo'lmadi. Excel (.xlsx) yoki CSV yuboring: F.I.Sh., Bo'lim, Lavozim, Telefon") from exc
    existing = {e.full_name.lower(): e for e in (await session.execute(select(Employee))).scalars()}
    created = updated = 0
    for row in rows:
        name = (row.get("full_name") or "").strip()
        if not name:
            continue
        emp = existing.get(name.lower())
        if emp is None:
            emp = Employee(full_name=name)
            session.add(emp)
            await session.flush()
            emp.folder = await accounts.unique_folder(session, row.get("folder") or name, emp.id)
            existing[name.lower()] = emp
            created += 1
        else:
            updated += 1
        for k in ("department", "position", "phone"):
            if row.get(k):
                setattr(emp, k, row[k])
    add_audit(session, "employee.import", actor=user.username, details={"created": created, "updated": updated})
    await session.commit()
    return {"created": created, "updated": updated, "total": len(rows)}


@router.get("/employees/{emp_id}")
async def get_employee(emp_id: int, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    emp = await _emp(session, emp_id)
    stats = await _stats(session)
    all_accounts = (await session.execute(select(TgAccount).where(TgAccount.employee_id == emp.id))).scalars().all()
    history = (await session.execute(select(TgAccountHistory).where(
        TgAccountHistory.account_id.in_([a.id for a in all_accounts] or [0])).order_by(TgAccountHistory.id.desc()).limit(100))).scalars()
    recent = (await session.execute(select(FileRecord).where(FileRecord.employee_id == emp.id, FileRecord.deleted_at.is_(None))
                                    .order_by(FileRecord.id.desc()).limit(20))).scalars()
    by_status = dict((await session.execute(select(FileRecord.status, func.count()).where(
        FileRecord.employee_id == emp.id, FileRecord.deleted_at.is_(None)).group_by(FileRecord.status))).all())
    acc_by_id = {a.id: a for a in all_accounts}
    return {**employee_out(emp, stats.get(emp.id)),
            "all_accounts": [account_out(a) for a in all_accounts],
            "history": [{"account": acc_by_id[h.account_id].display if h.account_id in acc_by_id else "", "field": h.field,
                         "old": h.old, "new": h.new, "at": h.at} for h in history],
            "recent_files": [serialize(r) for r in recent], "by_status": by_status}


@router.patch("/employees/{emp_id}")
async def update_employee(emp_id: int, body: EmployeeIn, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    emp = await _emp(session, emp_id)
    changes = {}
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "folder" and value is not None:
            value = await accounts.unique_folder(session, value, emp.id) if value.strip() else ""
        if field == "storage_id":
            value = value or None
            if value and await session.get(Storage, value) is None:
                raise HTTPException(400, "Saqlash joyi topilmadi")
        if getattr(emp, field) != value:
            changes[field] = [getattr(emp, field), value]
            setattr(emp, field, value)
    add_audit(session, "employee.update", actor=user.username, target=emp.full_name, details=changes)
    await session.commit()
    await session.refresh(emp, ["accounts"])
    return employee_out(emp)


class StatusBody(BaseModel):
    status: str


@router.post("/employees/{emp_id}/status")
async def set_status(emp_id: int, body: StatusBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    if body.status not in ("active", "blocked", "archived"):
        raise HTTPException(400, "Noto'g'ri holat")
    emp = await _emp(session, emp_id)
    old, emp.status = emp.status, body.status
    add_audit(session, f"employee.{body.status}", actor=user.username, target=emp.full_name, details={"old": old})
    await session.commit()
    return {"ok": True}


async def _invite_payload(session: AsyncSession, emp: Employee, actor: str, replace: bool = True) -> dict[str, Any]:
    settings = await settings_store.load(session)
    bot = settings.get("bot_username") or ""
    inv = await accounts.create_invite(session, emp, actor, replace)
    link = f"https://t.me/{bot}?start={inv.code}" if bot else ""
    png = qr.png(link, {"size": 400}, emp.full_name) if link else b""
    return {"employee_id": emp.id, "full_name": emp.full_name, "department": emp.department, "code": inv.code, "link": link,
            "expires_at": inv.expires_at, "qr_png": base64.b64encode(png).decode() if png else "",
            "bot_missing": not bot}


class InviteBody(BaseModel):
    replace: bool = True


@router.post("/employees/{emp_id}/invite")
async def invite(emp_id: int, body: InviteBody | None = None, session: AsyncSession = Depends(get_session),
                 user: Principal = Depends(admin)):
    emp = await _emp(session, emp_id)
    out = await _invite_payload(session, emp, user.username, body.replace if body else True)
    await session.commit()
    return out


class IdsBody(BaseModel):
    ids: list[int]


@router.post("/employees/invites")
async def bulk_invites(body: IdsBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    """Bir nechta xodimga taklif havolalari — chop etish uchun ro'yxat."""
    out = []
    for emp_id in body.ids:
        emp = await session.get(Employee, emp_id)
        if emp and emp.status != "archived":
            out.append(await _invite_payload(session, emp, user.username, replace=False))
    await session.commit()
    return out


@router.delete("/employees/{emp_id}/accounts/{acc_id}")
async def detach_account(emp_id: int, acc_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    acc = await session.get(TgAccount, acc_id)
    if acc is None or acc.employee_id != emp_id:
        raise HTTPException(404, "Akkaunt topilmadi")
    session.add(TgAccountHistory(account_id=acc.id, field="status", old=acc.status, new="detached"))
    acc.status = "detached"
    add_audit(session, "employee.account_detached", actor=user.username, target=acc.display)
    await session.commit()
    return {"ok": True}


# --- kirish so'rovlari ---
@router.get("/requests")
async def list_requests(status: str = "pending", session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    rows = (await session.execute(select(TgAccount).where(TgAccount.status.in_(status.split(",")))
                                  .order_by(TgAccount.first_seen.desc()))).scalars()
    return [account_out(a) for a in rows]


async def _acc(session: AsyncSession, acc_id: int) -> TgAccount:
    acc = await session.get(TgAccount, acc_id)
    if acc is None:
        raise HTTPException(404, "So'rov topilmadi")
    return acc


async def _tell(session: AsyncSession, acc: TgAccount, key: str) -> None:
    """Foydalanuvchiga botdan xabar (bot yoki token yo'q bo'lsa — jim o'tkaziladi)."""
    settings = await settings_store.load(session)
    if not settings.get("bot_token"):
        return
    try:
        async with TelegramClient.from_settings(settings) as tg:
            await tg.send_message(acc.telegram_id, settings_store.text(settings, acc.lang, key))
    except Exception:  # noqa: BLE001
        pass


class ApproveBody(BaseModel):
    full_name: str = ""
    department: str = ""
    position: str = ""
    phone: str = ""
    folder: str = ""


@router.post("/requests/{acc_id}/approve")
async def approve(acc_id: int, body: ApproveBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    acc = await _acc(session, acc_id)
    emp = await accounts.approve_as_new(session, acc, user.username, body.model_dump())
    await session.commit()
    await _tell(session, acc, "approved")
    return {"employee_id": emp.id}


class AttachBody(BaseModel):
    employee_id: int
    replace: bool = False


@router.post("/requests/{acc_id}/attach")
async def attach(acc_id: int, body: AttachBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    acc = await _acc(session, acc_id)
    emp = await _emp(session, body.employee_id)
    await accounts.attach_existing(session, acc, emp, user.username, body.replace)
    await session.commit()
    await _tell(session, acc, "approved")
    return {"ok": True}


class RejectBody(BaseModel):
    block: bool = False


@router.post("/requests/{acc_id}/reject")
async def reject(acc_id: int, body: RejectBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    acc = await _acc(session, acc_id)
    acc.status = "blocked" if body.block else "rejected"
    add_audit(session, "request.blocked" if body.block else "request.rejected", actor=user.username, target=acc.display)
    await session.commit()
    return {"ok": True}


@router.post("/requests/{acc_id}/reopen")
async def reopen(acc_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    acc = await _acc(session, acc_id)
    acc.status = "pending"
    add_audit(session, "request.reopened", actor=user.username, target=acc.display)
    await session.commit()
    return {"ok": True}

