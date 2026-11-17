"""Tashqi REST API v1 — boshqa botlar va tizimlar uchun. Autentifikatsiya: `Authorization: Bearer qd_live_...`."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import settings_store
from ..core.config import config
from ..db.models import ApiKey, Employee, FileRecord, IdempotencyKey, TgAccount
from ..db.session import get_session, session_scope
from ..services import qr
from ..services.audit import add_audit
from ..services.files import enqueue, refresh_link, revoke_link, save_upload, serialize
from .admin.files import storage_error
from .deps import api_key

router = APIRouter(prefix="/v1", tags=["API v1"])
FINAL = ("delivered", "failed")


class FileOut(BaseModel):
    id: int
    status: str = Field(description="queued | processing | retrying | delivered | failed")
    url: str = Field("", description="Ommaviy havola (tayyor bo'lsa)")
    qr_png_url: str = ""
    qr_base64: str = Field("", description="QR PNG, base64 (tayyor bo'lsa)")
    remote_path: str = ""
    expires_at: datetime | None = None
    original_name: str = ""
    size: int | None = None
    employee_id: int | None = None
    visibility: str = Field("", description="public | private")
    created_at: datetime | None = None
    error: dict[str, str] | None = Field(None, description="Xato bo'lsa: kind, title, hint")


async def _out(session: AsyncSession, rec: FileRecord, with_qr: bool = True) -> dict[str, Any]:
    d = serialize(rec)
    base = settings_store.public_base(await settings_store.load(session))
    data = {"id": rec.id, "status": rec.status, "url": rec.link_url, "remote_path": rec.remote_path,
            "expires_at": rec.link_expires_at, "original_name": rec.original_name, "size": rec.size,
            "employee_id": rec.employee_id, "created_at": rec.created_at, "error": d["error"], "visibility": d["visibility"],
            "qr_png_url": f"{base}{config.prefix}/api/v1/files/{rec.id}/qr.png" if rec.link_url else "",
            "qr_base64": ""}
    if with_qr and rec.link_url:
        settings = await settings_store.load(session)
        style = settings.get("qr_style") or {}
        data["qr_base64"] = base64.b64encode(qr.png(rec.link_url, style, qr.caption_for(
            style, rec.original_name, settings.get("company_name", "")))).decode()
    return data


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, datetime):
        return v.isoformat()
    return v


async def _resolve_employee(session: AsyncSession, employee_id: int | None, telegram_id: int | None) -> tuple[int | None, int | None]:
    if employee_id:
        emp = await session.get(Employee, employee_id)
        if emp is None or emp.status != "active":
            raise HTTPException(404, "Xodim topilmadi yoki faol emas")
        return emp.id, None
    if telegram_id:
        acc = (await session.execute(select(TgAccount).where(TgAccount.telegram_id == telegram_id))).scalar_one_or_none()
        if acc is None or acc.status != "active" or not acc.employee_id:
            raise HTTPException(404, "Bu Telegram ID tizimdagi faol xodimga biriktirilmagan")
        return acc.employee_id, acc.id
    return None, None


@router.post("/files", response_model=FileOut, responses={202: {"model": FileOut}},
             summary="Fayl yuklash va QR olish")
async def upload_file(
    file: UploadFile | None = File(None, description="Fayl (yoki source_url)"),
    source_url: str = Form("", description="Fayl shu manzildan yuklab olinadi"),
    employee_id: int | None = Form(None), telegram_id: int | None = Form(None),
    external_user: str = Form("", description="Tizimdan tashqi foydalanuvchi nomi (papka nomi bo'ladi)"),
    folder: str = Form("", description="Saqlash joyidagi papka (asosiy papkaga nisbatan)"),
    expire_days: int | None = Form(None), password: str = Form(""), caption: str = Form(""),
    visibility: str = Form("", description="public | private (bo'sh — panel sozlamasi)"),
    async_: bool = Query(False, alias="async", description="true — darhol 202, natija webhook orqali"),
    wait: int = Query(55, ge=0, le=120, description="Natijani necha soniya kutish"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    key: ApiKey = Depends(api_key("files:write")), session: AsyncSession = Depends(get_session),
):
    if idempotency_key:
        prev = (await session.execute(select(IdempotencyKey).where(IdempotencyKey.api_key_id == key.id,
                                                                   IdempotencyKey.key == idempotency_key))).scalar_one_or_none()
        if prev:
            rec = await session.get(FileRecord, prev.response.get("id"))
            if rec:
                return JSONResponse(_jsonable(await _out(session, rec)), status_code=200 if rec.status in FINAL else 202)
    if not file and not source_url:
        raise HTTPException(400, "file yoki source_url yuboring")
    emp_id, acc_id = await _resolve_employee(session, employee_id, telegram_id)
    settings = await settings_store.load(session)
    temp, size, name, mime = None, None, "", ""
    if file:
        temp, size = save_upload(file.file, file.filename or "fayl")
        name, mime = file.filename or "fayl", file.content_type or ""
        if size > int(settings.get("max_file_mb") or 100) * 1024 * 1024:
            temp.unlink(missing_ok=True)
            raise HTTPException(413, f"Fayl juda katta. Ruxsat: {settings.get('max_file_mb')} MB gacha")
    else:
        if not source_url.startswith(("http://", "https://")):
            raise HTTPException(400, "source_url http(s) manzil bo'lishi kerak")
        name = source_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "fayl"
    rec = await enqueue(session, source="api", original_name=name, actor=key.name, employee_id=emp_id, account_id=acc_id,
                        api_key_id=key.id, external_user=external_user or ("" if emp_id else key.name), temp_path=temp,
                        size=size, mime=mime, caption=caption,
                        options={"folder": folder, "expire_days": expire_days, "password": password,
                                 **({"visibility": visibility} if visibility in ("public", "private") else {}),
                                 **({"source_url": source_url} if source_url else {})})
    if idempotency_key:
        session.add(IdempotencyKey(api_key_id=key.id, key=idempotency_key, response={"id": rec.id}))
    add_audit(session, "api.file_upload", actor=key.name, actor_kind="api", target=name)
    await session.commit()
    fid = rec.id
    if not async_ and wait:
        # worker faylni ishlaydi; shu vaqt ichida tayyor bo'lsa — natija darhol qaytadi
        deadline = asyncio.get_running_loop().time() + wait
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.5)
            async with session_scope() as s:
                status = (await s.execute(select(FileRecord.status).where(FileRecord.id == fid))).scalar_one()
            if status in FINAL:
                break
    async with session_scope() as s:
        rec = await s.get(FileRecord, fid)
        data = await _out(s, rec)
    return JSONResponse(_jsonable(data), status_code=200 if rec.status in FINAL else 202)


async def _own(session: AsyncSession, key: ApiKey, file_id: int) -> FileRecord:
    rec = await session.get(FileRecord, file_id)
    if rec is None or rec.deleted_at is not None or rec.api_key_id != key.id:
        raise HTTPException(404, "Fayl topilmadi")
    return rec


@router.get("/files/{file_id}", response_model=FileOut, summary="Fayl holati")
async def get_file(file_id: int, key: ApiKey = Depends(api_key("files:read")), session: AsyncSession = Depends(get_session)):
    return await _out(session, await _own(session, key, file_id))


@router.get("/files", summary="Fayllar ro'yxati (shu kalit bilan yuklanganlar)")
async def list_files(employee_id: int | None = None, status: str = "", page: int = Query(1, ge=1), page_size: int = Query(50, le=200),
                     key: ApiKey = Depends(api_key("files:read")), session: AsyncSession = Depends(get_session)):
    conds = [FileRecord.api_key_id == key.id, FileRecord.deleted_at.is_(None)]
    if employee_id:
        conds.append(FileRecord.employee_id == employee_id)
    if status:
        conds.append(FileRecord.status.in_(status.split(",")))
    total = (await session.execute(select(func.count()).select_from(FileRecord).where(*conds))).scalar_one()
    rows = (await session.execute(select(FileRecord).where(*conds).order_by(FileRecord.id.desc())
                                  .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [await _out(session, r, with_qr=False) for r in rows], "total": total}


@router.get("/files/{file_id}/qr.png", summary="QR rasm (PNG)", response_class=Response)
async def file_qr_png(file_id: int, size: int | None = Query(None, ge=200, le=2000), logo: bool | None = None,
                      key: ApiKey = Depends(api_key("files:read")), session: AsyncSession = Depends(get_session)):
    rec = await _own(session, key, file_id)
    if not rec.link_url:
        raise HTTPException(409, "Fayl hali tayyor emas yoki havola bekor qilingan")
    settings = await settings_store.load(session)
    style = {**(settings.get("qr_style") or {}), **({"size": size} if size else {}), **({"logo": logo} if logo is not None else {})}
    return Response(qr.png(rec.link_url, style, qr.caption_for(style, rec.original_name, settings.get("company_name", ""))),
                    media_type="image/png")


@router.get("/files/{file_id}/qr.pdf", summary="QR (PDF, chop etish uchun)", response_class=Response)
async def file_qr_pdf(file_id: int, key: ApiKey = Depends(api_key("files:read")), session: AsyncSession = Depends(get_session)):
    rec = await _own(session, key, file_id)
    if not rec.link_url:
        raise HTTPException(409, "Fayl hali tayyor emas yoki havola bekor qilingan")
    settings = await settings_store.load(session)
    style = settings.get("qr_style") or {}
    return Response(qr.pdf(rec.link_url, style, qr.caption_for(style, rec.original_name, settings.get("company_name", ""))),
                    media_type="application/pdf")


class LinkIn(BaseModel):
    expire_days: int | None = None
    password: str | None = None


@router.post("/files/{file_id}/link", response_model=FileOut, summary="Havolani yangilash")
async def link_refresh(file_id: int, body: LinkIn | None = None, key: ApiKey = Depends(api_key("files:write")),
                       session: AsyncSession = Depends(get_session)):
    rec = await _own(session, key, file_id)
    settings = await settings_store.load(session)
    try:
        await refresh_link(session, rec, settings, body.expire_days if body else None, body.password if body else None)
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    add_audit(session, "api.link_refresh", actor=key.name, actor_kind="api", target=rec.original_name)
    await session.commit()
    return await _out(session, rec)


@router.delete("/files/{file_id}/link", summary="Havolani bekor qilish")
async def link_revoke(file_id: int, key: ApiKey = Depends(api_key("files:write")), session: AsyncSession = Depends(get_session)):
    rec = await _own(session, key, file_id)
    try:
        await revoke_link(session, rec)
    except Exception as exc:  # noqa: BLE001
        raise storage_error(exc) from exc
    from ..services.pipeline import enqueue_webhook
    await enqueue_webhook(session, rec, "link.revoked")
    add_audit(session, "api.link_revoke", actor=key.name, actor_kind="api", target=rec.original_name)
    await session.commit()
    return {"ok": True}


class QrIn(BaseModel):
    url: str
    size: int | None = Field(None, ge=200, le=2000)
    fg: str | None = None
    bg: str | None = None
    caption: str = ""
    logo: bool = False
    format: str = Field("png", description="png | pdf | base64")


@router.post("/qr", summary="Istalgan havoladan QR", response_class=Response)
async def make_qr(body: QrIn, key: ApiKey = Depends(api_key("qr:generate")), session: AsyncSession = Depends(get_session)):
    settings = await settings_store.load(session)
    style = {**(settings.get("qr_style") or {}), **{k: v for k, v in (("size", body.size), ("fg", body.fg), ("bg", body.bg)) if v},
             "logo": body.logo}
    if body.format == "pdf":
        return Response(qr.pdf(body.url, style, body.caption), media_type="application/pdf")
    data = qr.png(body.url, style, body.caption)
    if body.format == "base64":
        return JSONResponse({"qr_base64": base64.b64encode(data).decode()})
    return Response(data, media_type="image/png")


@router.get("/employees", summary="Xodimlar ro'yxati")
async def employees(q: str = "", key: ApiKey = Depends(api_key("employees:read")), session: AsyncSession = Depends(get_session)):
    query = select(Employee).where(Employee.status == "active").order_by(Employee.full_name)
    if q:
        query = query.where(Employee.full_name.ilike(f"%{q}%"))
    return [{"id": e.id, "full_name": e.full_name, "department": e.department, "position": e.position,
             "telegram_ids": [a.telegram_id for a in e.accounts if a.status == "active"]}
            for e in (await session.execute(query)).scalars()]


@router.get("/health", summary="Servis holati (kalitsiz)")
async def health():
    return {"ok": True, "service": "qrdrive", "time": datetime.now(timezone.utc)}
