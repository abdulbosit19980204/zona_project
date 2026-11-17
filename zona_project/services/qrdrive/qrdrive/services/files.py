"""Fayl yozuvlari: navbatga qo'yish, havolalar (provayder yoki tizim havolasi), API ko'rinishi."""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy.ext.asyncio import AsyncSession

from .. import settings_store
from ..core.config import config
from ..core.crypto import decrypt, encrypt, hash_password, token
from ..core.errors import NotSupported, human
from ..db.models import FileEvent, FileRecord, Storage, SystemLink
from ..storage import registry
from ..storage.base import RemoteFile
from .naming import safe_name


def spool_path(prefix: str) -> Path:
    config.spool_dir.mkdir(parents=True, exist_ok=True)
    return config.spool_dir / f"{prefix}_{token(9)}"


def save_upload(fh: BinaryIO, original_name: str) -> tuple[Path, int]:
    path = spool_path("up")
    with open(path, "wb") as out:
        shutil.copyfileobj(fh, out, 1024 * 1024)
    return path, path.stat().st_size


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


async def enqueue(session: AsyncSession, *, source: str, original_name: str, actor: str = "", employee_id: int | None = None,
                  account_id: int | None = None, api_key_id: int | None = None, external_user: str = "",
                  temp_path: Path | None = None, size: int | None = None, mime: str = "", caption: str = "",
                  options: dict[str, Any] | None = None, tg: dict[str, Any] | None = None,
                  storage_id: int | None = None) -> FileRecord:
    opts = dict(options or {})
    if opts.get("password"):
        opts["password_enc"] = encrypt(str(opts.pop("password")))
    rec = FileRecord(source=source, original_name=safe_name(original_name), actor=actor, employee_id=employee_id,
                     account_id=account_id, api_key_id=api_key_id, external_user=external_user,
                     temp_path=str(temp_path or ""), size=size,
                     mime=mime if mime and mime != "application/octet-stream" else guess_mime(original_name), caption=caption,
                     options=opts, status="queued", stage="received", next_attempt_at=datetime.now(timezone.utc),
                     storage_id=storage_id)
    if tg:
        rec.tg_chat_id, rec.tg_file_id, rec.tg_status_msg_id = tg.get("chat_id"), tg.get("file_id", ""), tg.get("status_msg_id")
    session.add(rec)
    await session.flush()
    await session.refresh(rec, ["employee", "storage"])
    session.add(FileEvent(file_id=rec.id, stage="received", message=source))
    return rec


def link_password(rec: FileRecord, settings: dict[str, Any]) -> str:
    return decrypt(rec.options.get("password_enc", "")) or settings.get("link_password", "")


def link_expiry(rec: FileRecord, settings: dict[str, Any]) -> datetime | None:
    days = rec.options.get("expire_days")
    days = int(settings.get("link_expire_days") or 0) if days in (None, "") else int(days)
    return datetime.now(timezone.utc) + timedelta(days=days) if days > 0 else None


async def create_system_link(session: AsyncSession, rec: FileRecord, expires_at: datetime | None, password: str,
                             base_url: str | None = None) -> str:
    link = SystemLink(token=token(24), file_id=rec.id, expires_at=expires_at,
                      password_hash=hash_password(password) if password else "")
    session.add(link)
    rec.link_url = f"{base_url or config.public_base_url}{config.prefix}/s/{link.token}"
    rec.link_id, rec.link_kind = link.token, "system"
    rec.link_expires_at, rec.link_has_password = expires_at, bool(password)
    return rec.link_url


async def create_link(session: AsyncSession, rec: FileRecord, storage: Storage, provider, settings: dict[str, Any]) -> str:
    expires_at, password = link_expiry(rec, settings), link_password(rec, settings)
    if storage.link_mode == "system" or not provider.supports_links:
        return await create_system_link(session, rec, expires_at, password, settings_store.public_base(settings))
    try:
        link = await provider.create_public_link(RemoteFile(path=rec.remote_path, id=rec.remote_id), expires_at, password or None)
    except NotSupported:
        return await create_system_link(session, rec, expires_at, password, settings_store.public_base(settings))
    rec.link_url, rec.link_id, rec.link_kind = link.url, link.id, "provider"
    rec.link_expires_at, rec.link_has_password = expires_at, bool(password)
    return rec.link_url


async def revoke_link(session: AsyncSession, rec: FileRecord) -> None:
    if rec.link_kind == "system" and rec.link_id:
        link = await session.get(SystemLink, rec.link_id)
        if link:
            link.revoked = True
    elif rec.link_kind == "provider" and rec.link_id and rec.storage:
        provider = registry.build(rec.storage)
        try:
            await provider.revoke_public_link(rec.link_id)
        finally:
            await provider.close()
    rec.link_url, rec.link_id, rec.link_kind = "", "", ""
    rec.link_expires_at, rec.link_has_password = None, False


async def refresh_link(session: AsyncSession, rec: FileRecord, settings: dict[str, Any],
                       expire_days: int | None = None, password: str | None = None) -> str:
    if rec.storage is None or not rec.remote_path:
        raise NotSupported("fayl hali saqlanmagan")
    opts = dict(rec.options)
    if expire_days is not None:
        opts["expire_days"] = expire_days
    if password is not None:
        opts["password_enc"] = encrypt(password) if password else ""
    rec.options = opts
    await revoke_link(session, rec)
    provider = registry.build(rec.storage)
    try:
        return await create_link(session, rec, rec.storage, provider, settings)
    finally:
        await provider.close()


STATUS_LABEL = {"queued": "Navbatda", "processing": "Ishlanmoqda", "retrying": "Qayta urinilmoqda",
                "delivered": "Tayyor", "failed": "Xato"}


def serialize(rec: FileRecord, *, full: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": rec.id, "status": rec.status, "status_label": STATUS_LABEL.get(rec.status, rec.status), "stage": rec.stage,
        "source": rec.source, "original_name": rec.original_name, "stored_name": rec.stored_name, "size": rec.size,
        "mime": rec.mime, "caption": rec.caption, "employee_id": rec.employee_id,
        "employee_name": rec.employee.full_name if rec.employee else (rec.external_user or ""),
        "department": rec.employee.department if rec.employee else "",
        "storage_id": rec.storage_id, "storage_name": rec.storage.name if rec.storage else "",
        "remote_path": rec.remote_path, "url": rec.link_url, "link_kind": rec.link_kind,
        "expires_at": rec.link_expires_at, "has_password": rec.link_has_password, "downloads": rec.downloads,
        "attempts": rec.attempts, "created_at": rec.created_at, "finished_at": rec.finished_at,
        "deleted_at": rec.deleted_at, "duplicate_of": rec.duplicate_of, "durations": rec.durations or {},
        "error": human(rec.error_kind) if rec.error_kind else None,
    }
    if full:
        data["options"] = {k: v for k, v in (rec.options or {}).items() if not k.endswith("_enc")}
        data["external_user"] = rec.external_user
        data["actor"] = rec.actor
    return data
