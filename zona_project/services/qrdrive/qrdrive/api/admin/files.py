"""Panel: fayllar — jadval, papka brauzeri, ko'rish/yuklab olish, QR, havola, nom/ko'chirish, savat, vebdan yuklash."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import settings_store
from ...core.errors import QRDriveError, classify, human
from ...core.security import Principal
from ...db.models import Employee, FileEvent, FileRecord, Storage
from ...db.session import get_session
from ...services import pipeline, qr
from ...services.audit import add_audit
from ...services.archive import is_archive
from ...services.files import enqueue, find_previous, guess_mime, refresh_link, revoke_link, save_upload, serialize
from ...services.naming import safe_name
from ...storage import registry
from ..deps import admin, viewer

router = APIRouter(prefix="/files", tags=["admin: files"])

TYPE_FILTERS = {
    "image": FileRecord.mime.like("image/%"), "video": FileRecord.mime.like("video/%"),
    "audio": FileRecord.mime.like("audio/%"), "pdf": FileRecord.mime == "application/pdf",
}


def storage_error(exc: Exception) -> HTTPException:
    msg = human(classify(exc).kind)
    return HTTPException(502, f"{msg['title']}. {msg['hint']}")


async def _get(session: AsyncSession, file_id: int) -> FileRecord:
    rec = await session.get(FileRecord, file_id)
    if rec is None:
        raise HTTPException(404, "Fayl topilmadi")
    return rec


def _filters(q: str, employee_id: int | None, department: str, status: str, source: str, storage_id: int | None,
             date_from: date | None, date_to: date | None, ftype: str, trash: bool, versions: bool = False) -> list[Any]:
    conds: list[Any] = [FileRecord.deleted_at.isnot(None) if trash else FileRecord.deleted_at.is_(None)]
    if not versions:
        conds.append(FileRecord.replaced_by.is_(None))
    if not status:
        conds.append(FileRecord.status != "merged")  # papkaga yig'ilgan guruh a'zolari  # eski versiyalar ro'yxatda ko'rinmaydi (fayl kartasida bor)
    if q:
        like = f"%{q}%"
        conds.append(or_(FileRecord.original_name.ilike(like), FileRecord.stored_name.ilike(like),
                         FileRecord.caption.ilike(like), FileRecord.remote_path.ilike(like),
                         FileRecord.employee.has(Employee.full_name.ilike(like))))
    if employee_id:
        conds.append(FileRecord.employee_id == employee_id)
    if department:
        conds.append(FileRecord.employee.has(Employee.department == department))
    if status:
        conds.append(FileRecord.status.in_(status.split(",")))
    if source:
        conds.append(FileRecord.source == source)
    if storage_id:
        conds.append(FileRecord.storage_id == storage_id)
    if date_from:
        conds.append(FileRecord.created_at >= datetime.combine(date_from, datetime.min.time(), timezone.utc))
    if date_to:
        conds.append(FileRecord.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), timezone.utc))
    if ftype == "other":
        conds.append(~or_(*TYPE_FILTERS.values()))
    elif ftype in TYPE_FILTERS:
        conds.append(TYPE_FILTERS[ftype])
    return conds


@router.get("")
async def list_files(q: str = "", employee_id: int | None = None, department: str = "", status: str = "", source: str = "",
                     storage_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                     type: str = "", trash: bool = False, versions: bool = False, page: int = Query(1, ge=1),
                     page_size: int = Query(50, le=500), session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    conds = _filters(q, employee_id, department, status, source, storage_id, date_from, date_to, type, trash, versions)
    total = (await session.execute(select(func.count()).select_from(FileRecord).where(*conds))).scalar_one()
    rows = (await session.execute(select(FileRecord).where(*conds).order_by(FileRecord.id.desc())
                                  .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [serialize(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/export.csv")
async def export_csv(q: str = "", employee_id: int | None = None, department: str = "", status: str = "", source: str = "",
                     storage_id: int | None = None, date_from: date | None = None, date_to: date | None = None, type: str = "",
                     session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    conds = _filters(q, employee_id, department, status, source, storage_id, date_from, date_to, type, False)
    rows = (await session.execute(select(FileRecord).where(*conds).order_by(FileRecord.id.desc()).limit(50000))).scalars()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Sana", "Xodim", "Bo'lim", "Fayl", "Hajm (bayt)", "Holat", "Manba", "Saqlash joyi", "Yo'l", "Havola"])
    for r in rows:
        d = serialize(r)
        w.writerow([r.id, r.created_at.isoformat(), d["employee_name"], d["department"], r.original_name, r.size or "",
                    d["status_label"], r.source, d["storage_name"], r.remote_path, r.link_url])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=qrdrive-files.csv"})


@router.get("/folders")
async def folders(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    """Papka brauzeri ildizi: xodim papkalari (fayl soni, hajmi)."""
    rows = (await session.execute(
        select(FileRecord.employee_id, func.count(), func.coalesce(func.sum(FileRecord.size), 0), func.max(FileRecord.created_at))
        .where(FileRecord.deleted_at.is_(None), FileRecord.status == "delivered", FileRecord.duplicate_of.is_(None))
        .group_by(FileRecord.employee_id))).all()
    stats = {r[0]: (r[1], r[2], r[3]) for r in rows}
    emps = (await session.execute(select(Employee).order_by(Employee.full_name))).scalars().all()
    out = [{"employee_id": e.id, "name": e.full_name, "folder": e.folder, "department": e.department, "status": e.status,
            "storage_id": e.storage_id, "count": stats.get(e.id, (0, 0, None))[0], "size": stats.get(e.id, (0, 0, None))[1],
            "last_at": stats.get(e.id, (0, 0, None))[2]} for e in emps]
    if None in stats:
        c, s, last = stats[None]
        out.append({"employee_id": None, "name": "API / tashqi", "folder": "API", "department": "", "status": "active",
                    "storage_id": None, "count": c, "size": s, "last_at": last})
    return out


@router.get("/browse")
async def browse(storage_id: int, path: str = "/", session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    """Saqlash joyidagi papka tarkibi; tizimda ro'yxatga olinmagan fayllar belgilanadi."""
    storage = await session.get(Storage, storage_id)
    if storage is None:
        raise HTTPException(404, "Saqlash joyi topilmadi")
    provider = registry.build(storage)
    try:
        entries = await provider.list(path or storage.base_folder or "/")
    except QRDriveError as exc:
        raise storage_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    finally:
        await provider.close()
    paths = [e.path for e in entries if not e.is_dir]
    known = {}
    if paths:
        for r in (await session.execute(select(FileRecord).where(FileRecord.storage_id == storage_id,
                                                                 FileRecord.remote_path.in_(paths),
                                                                 FileRecord.duplicate_of.is_(None)))).scalars():
            known[r.remote_path] = r
    return {"path": path, "base": storage.base_folder, "entries": [
        {"name": e.name, "path": e.path, "is_dir": e.is_dir, "size": e.size, "modified": e.modified,
         "file": serialize(known[e.path]) if e.path in known else None, "registered": e.is_dir or e.path in known}
        for e in entries]}


@router.get("/{file_id}")
async def get_file(file_id: int, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    rec = await _get(session, file_id)
    events = (await session.execute(select(FileEvent).where(FileEvent.file_id == file_id).order_by(FileEvent.id))).scalars()
    versions = []
    if rec.kind == "file" and rec.remote_path and rec.storage_id:
        versions = [{"id": v.id, "version": v.version, "size": v.size, "created_at": v.created_at, "actor": v.actor,
                     "current": v.replaced_by is None, "original_name": v.original_name}
                    for v in (await session.execute(select(FileRecord).where(
                        FileRecord.storage_id == rec.storage_id, FileRecord.remote_path == rec.remote_path,
                        FileRecord.status == "delivered", FileRecord.duplicate_of.is_(None)).order_by(FileRecord.version.desc()))).scalars()]
    return {**serialize(rec, full=True), "versions": versions if len(versions) > 1 else [], "events": [
        {"stage": e.stage, "ok": e.ok, "message": e.message, "duration_ms": e.duration_ms, "at": e.at} for e in events]}


@router.post("/upload")
async def upload(files: list[UploadFile] = File(...), employee_id: int | None = Form(None), folder: str = Form(""),
                 expire_days: int | None = Form(None), caption: str = Form(""), visibility: str = Form(""),
                 replace: bool = Form(False), extract: bool = Form(False),
                 session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    """Vebdan yuklash — Telegram bilan bir xil jarayon (worker yuklaydi va havola yaratadi)."""
    settings = await settings_store.load(session)
    max_bytes = int(settings.get("max_file_mb") or 100) * 1024 * 1024
    created = []
    for f in files:
        path, size = save_upload(f.file, f.filename or "fayl")
        if size > max_bytes:
            path.unlink(missing_ok=True)
            raise HTTPException(413, f"«{f.filename}» juda katta. Ruxsat: {settings.get('max_file_mb')} MB gacha.")
        name = f.filename or "fayl"
        extra: dict[str, Any] = {"visibility": visibility} if visibility in ("public", "private") else {}
        prev = await find_previous(session, employee_id=employee_id, api_key_id=None, name=name) if replace else None
        if prev is not None:
            extra["replace_of"] = prev.id
        elif extract and is_archive(name):
            extra["archive"] = "folder"
        rec = await enqueue(session, source="web", original_name=name, actor=user.username,
                            employee_id=employee_id, temp_path=path, size=size, mime=f.content_type or "",
                            caption=caption, options={"folder": folder, "expire_days": expire_days, **extra})
        created.append(rec)
    add_audit(session, "file.upload_web", actor=user.username, target=", ".join(r.original_name for r in created))
    await session.commit()
    return [serialize(r) for r in created]


class Ids(BaseModel):
    ids: list[int]
    action: str = ""


@router.post("/bulk")
async def bulk(body: Ids, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    done = 0
    for fid in body.ids:
        rec = await session.get(FileRecord, fid)
        if rec is None:
            continue
        if body.action == "retry" and rec.status == "failed":
            await pipeline.retry(session, rec)
        elif body.action == "delete" and rec.deleted_at is None:
            rec.deleted_at = datetime.now(timezone.utc)
        elif body.action == "restore" and rec.deleted_at is not None:
            rec.deleted_at = None
        elif body.action == "purge" and rec.deleted_at is not None:
            await _purge(session, rec)
        else:
            continue
        done += 1
    add_audit(session, f"file.bulk_{body.action}", actor=user.username, details={"ids": body.ids, "done": done})
    await session.commit()
    return {"done": done}


class RelinkBody(BaseModel):
    ids: list[int] | None = None
    storage_id: int | None = None
    only_system: bool = True  # faqat tizim havolasi berilgan fayllar


@router.post("/relink")
async def relink(body: RelinkBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    """Havolalarni qayta yaratish (masalan, saqlash joyi «o'z havolasi» rejimiga o'tkazilgach)."""
    q = select(FileRecord).where(FileRecord.status == "delivered", FileRecord.deleted_at.is_(None))
    if body.ids:
        q = q.where(FileRecord.id.in_(body.ids))
    if body.storage_id:
        q = q.where(FileRecord.storage_id == body.storage_id)
    if body.only_system and not body.ids:
        q = q.where(FileRecord.link_kind == "system")
    recs = list((await session.execute(q.order_by(FileRecord.id).limit(500))).scalars())
    settings = await settings_store.load(session)
    from ...services.files import relink as do_relink
    result = await do_relink(session, recs, settings)
    add_audit(session, "file.relink", actor=user.username, details={"done": result["done"], "failed": len(result["failed"])})
    await session.commit()
    return result


@router.post("/{file_id}/retry")
async def retry(file_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    if rec.status not in ("failed", "retrying"):
        raise HTTPException(400, "Faqat xato bilan tugagan faylni qayta urinish mumkin")
    await pipeline.retry(session, rec)
    add_audit(session, "file.retry", actor=user.username, target=rec.original_name)
    await session.commit()
    return serialize(rec)


@router.delete("/{file_id}")
async def to_trash(file_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    rec.deleted_at = datetime.now(timezone.utc)
    add_audit(session, "file.trash", actor=user.username, target=rec.original_name)
    await session.commit()
    return {"ok": True}


@router.post("/{file_id}/restore")
async def restore(file_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    rec.deleted_at = None
    add_audit(session, "file.restore", actor=user.username, target=rec.original_name)
    await session.commit()
    return serialize(rec)


async def _purge(session: AsyncSession, rec: FileRecord) -> None:
    """Butunlay o'chirish: havola bekor qilinadi va fayl saqlash joyidan o'chiriladi —
    agar shu fayl/havolani boshqa yozuv (takroriy nusxa yoki boshqa versiya) ishlatmasa."""
    shared = (await session.execute(select(func.count()).select_from(FileRecord).where(
        FileRecord.id != rec.id, FileRecord.deleted_at.is_(None),
        or_(FileRecord.duplicate_of == rec.id,
            and_(FileRecord.storage_id == rec.storage_id, FileRecord.remote_path == rec.remote_path, FileRecord.remote_path != ""))
    ))).scalar_one()
    if rec.link_url and not rec.duplicate_of and not shared:
        try:
            await revoke_link(session, rec)
        except Exception:  # noqa: BLE001 — havola allaqachon yo'q bo'lishi mumkin
            pass
    if rec.storage and rec.remote_path and not rec.duplicate_of and not shared:
        provider = registry.build(rec.storage)
        try:
            await provider.delete(rec.remote_path)
        finally:
            await provider.close()
    await session.delete(rec)


@router.delete("/{file_id}/purge")
async def purge(file_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    name = rec.original_name
    try:
        await _purge(session, rec)
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    add_audit(session, "file.purge", actor=user.username, target=name)
    await session.commit()
    return {"ok": True}


class LinkBody(BaseModel):
    expire_days: int | None = None
    password: str | None = None
    visibility: str | None = None


@router.post("/{file_id}/link")
async def link_refresh(file_id: int, body: LinkBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    settings = await settings_store.load(session)
    if body.visibility in ("public", "private"):
        rec.options = {**(rec.options or {}), "visibility": body.visibility}
    try:
        await refresh_link(session, rec, settings, body.expire_days, body.password)
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    add_audit(session, "file.link_refresh", actor=user.username, target=rec.original_name,
              details={"expire_days": body.expire_days, "password": "••••••" if body.password else None})
    await session.commit()
    return serialize(rec)


@router.delete("/{file_id}/link")
async def link_revoke(file_id: int, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    try:
        await revoke_link(session, rec)
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    add_audit(session, "file.link_revoke", actor=user.username, target=rec.original_name)
    await session.commit()
    return serialize(rec)


class RenameBody(BaseModel):
    name: str


@router.post("/{file_id}/rename")
async def rename(file_id: int, body: RenameBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    new = safe_name(body.name)
    if not rec.storage or not rec.remote_path:
        raise HTTPException(400, "Fayl hali saqlanmagan")
    provider = registry.build(rec.storage)
    try:
        old = rec.remote_path
        rec.remote_path = await provider.rename(rec.remote_path, new)
        rec.remote_id, rec.stored_name = rec.remote_path, new
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    finally:
        await provider.close()
    add_audit(session, "file.rename", actor=user.username, target=new, details={"old": old})
    await session.commit()
    return serialize(rec)


class MoveBody(BaseModel):
    folder: str


@router.post("/{file_id}/move")
async def move(file_id: int, body: MoveBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    rec = await _get(session, file_id)
    if not rec.storage or not rec.remote_path:
        raise HTTPException(400, "Fayl hali saqlanmagan")
    provider = registry.build(rec.storage)
    try:
        old = rec.remote_path
        rec.remote_path = await provider.move(rec.remote_path, body.folder)
        rec.remote_id = rec.remote_path
        # shu faylning boshqa versiyalari va takroriy nusxalari ham yangi joyga ishora qilsin
        for other in (await session.execute(select(FileRecord).where(
                FileRecord.id != rec.id, FileRecord.storage_id == rec.storage_id, FileRecord.remote_path == old))).scalars():
            other.remote_path, other.remote_id = rec.remote_path, rec.remote_path
        if rec.link_kind == "provider":  # provayder havolasi eski yo'lga bog'langan — yangilanadi
            settings = await settings_store.load(session)
            await refresh_link(session, rec, settings)
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    finally:
        await provider.close()
    add_audit(session, "file.move", actor=user.username, target=rec.original_name, details={"old": old, "new": rec.remote_path})
    await session.commit()
    return serialize(rec)


@router.get("/{file_id}/qr.png")
async def qr_png(file_id: int, size: int | None = None, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    rec = await _get(session, file_id)
    if not rec.link_url:
        raise HTTPException(400, "Faylda faol havola yo'q")
    settings = await settings_store.load(session)
    style = {**(settings.get("qr_style") or {}), **({"size": size} if size else {})}
    data = qr.png(rec.link_url, style, qr.caption_for(style, rec.original_name, settings.get("company_name", "")))
    return Response(data, media_type="image/png", headers={"Content-Disposition": f"inline; filename=qr-{rec.id}.png"})


@router.get("/{file_id}/qr.pdf")
async def qr_pdf(file_id: int, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    rec = await _get(session, file_id)
    if not rec.link_url:
        raise HTTPException(400, "Faylda faol havola yo'q")
    settings = await settings_store.load(session)
    style = settings.get("qr_style") or {}
    data = qr.pdf(rec.link_url, style, qr.caption_for(style, rec.original_name, settings.get("company_name", "")))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename=qr-{rec.id}.pdf"})


async def stream_remote(storage: Storage, path: str, filename: str, mime: str, download: bool) -> StreamingResponse:
    provider = registry.build(storage)
    gen = provider.open_stream(path)
    try:
        first = await gen.__anext__()
    except StopAsyncIteration:
        first = b""
    except Exception as exc:  # noqa: BLE001
        await provider.close()
        raise storage_error(exc) from exc

    async def body():
        try:
            if first:
                yield first
            async for chunk in gen:
                yield chunk
        finally:
            await provider.close()

    disp = "attachment" if download else "inline"
    return StreamingResponse(body(), media_type=mime or "application/octet-stream",
                             headers={"Content-Disposition": f"{disp}; filename*=UTF-8''{quote(filename)}",
                                      "Cache-Control": "private, max-age=300"})


@router.get("/{file_id}/content")
async def content(file_id: int, download: bool = False, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    """Ko'rish/yuklab olish — backend orqali (saqlash joyi parollari brauzerga chiqmaydi)."""
    rec = await _get(session, file_id)
    if not rec.storage or not rec.remote_path:
        raise HTTPException(400, "Fayl hali saqlanmagan")
    return await stream_remote(rec.storage, rec.remote_path, rec.stored_name or rec.original_name, rec.mime, download)


@router.get("/{file_id}/items/{index}")
async def folder_item(file_id: int, index: int, download: bool = False, session: AsyncSession = Depends(get_session),
                      _: Principal = Depends(viewer)):
    """Papka (ochilgan arxiv) ichidagi fayl."""
    rec = await _get(session, file_id)
    items = rec.items or []
    if rec.kind != "folder" or not 0 <= index < len(items) or not rec.storage:
        raise HTTPException(404, "Fayl topilmadi")
    name = items[index]["name"]
    return await stream_remote(rec.storage, f"{rec.remote_path.rstrip('/')}/{name}", name.rsplit("/", 1)[-1], guess_mime(name), download)


@router.get("/raw/{storage_id}")
async def raw(storage_id: int, path: str, download: bool = False, session: AsyncSession = Depends(get_session),
              _: Principal = Depends(viewer)):
    """Tizimda ro'yxatga olinmagan faylni (papka brauzeridan) ochish."""
    storage = await session.get(Storage, storage_id)
    if storage is None:
        raise HTTPException(404, "Saqlash joyi topilmadi")
    name = path.rsplit("/", 1)[-1]
    return await stream_remote(storage, path, name, guess_mime(name), download)
