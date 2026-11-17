"""Fayl jarayoni: received → downloading → uploading → sharing → qr_generated → delivered (yoki failed).
Har bosqich FileEvent sifatida vaqti bilan yoziladi. Xatoda 3 marta qayta urinish (10 s, 60 s, 5 daq)."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import settings_store
from ..core.config import config
from ..core.errors import (FileTooBig, FileTypeNotAllowed, NoStorage, QRDriveError, StorageNotFound,
                           StorageUnavailable, TelegramError, classify, human)
from ..core.logging import trace_id
from ..db.models import ApiKey, FileEvent, FileRecord, Storage, TgAccount, WebhookDelivery
from ..storage import registry
from ..storage.base import join
from . import qr
from .accounts import employee_folder, unique_folder
from .audit import notify
from .files import create_link, serialize, sha256_of, spool_path
from .naming import render_filename, render_folder, safe_name
from .telegram import TelegramClient

log = logging.getLogger("qrdrive.pipeline")

RETRY_DELAYS = [10, 60, 300]
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
LOCK_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_next(session: AsyncSession) -> int | None:
    """Navbatdagi faylni band qiladi (bir nechta worker bo'lsa ham bitta fayl bitta workerda)."""
    now = _now()
    due = and_(FileRecord.status.in_(("queued", "retrying")), FileRecord.deleted_at.is_(None),
               or_(FileRecord.next_attempt_at.is_(None), FileRecord.next_attempt_at <= now),
               or_(FileRecord.locked_until.is_(None), FileRecord.locked_until < now))
    fid = (await session.execute(select(FileRecord.id).where(due).order_by(FileRecord.id).limit(1))).scalar_one_or_none()
    if fid is None:
        return None
    res = await session.execute(update(FileRecord).where(FileRecord.id == fid, due)
                                .values(status="processing", locked_until=now + timedelta(minutes=LOCK_MINUTES)))
    await session.commit()
    return fid if res.rowcount else None


def allowed(name: str, allowed_types: str) -> bool:
    types = {t.strip().lower().lstrip(".") for t in (allowed_types or "").split(",") if t.strip()}
    if not types:
        return True
    return name.rsplit(".", 1)[-1].lower() in types if "." in name else False


class Ctx:
    def __init__(self, session: AsyncSession, rec: FileRecord, settings: dict[str, Any]):
        self.session, self.rec, self.settings = session, rec, settings
        self.tg: TelegramClient | None = None
        self.lang = settings.get("default_lang", "uz")
        self.local_file: Path | None = None
        self.cleanup: list[Path] = []

    def text(self, key: str, **kw: Any) -> str:
        return settings_store.text(self.settings, self.lang, key, **kw)

    async def status_msg(self, key: str, **kw: Any) -> None:
        if self.tg and self.rec.tg_chat_id and self.rec.tg_status_msg_id:
            await self.tg.edit_message(self.rec.tg_chat_id, self.rec.tg_status_msg_id, self.text(key, **kw))

    @asynccontextmanager
    async def stage(self, name: str):
        self.rec.stage = name
        start = time.perf_counter()
        try:
            yield
        except BaseException as exc:
            ms = int((time.perf_counter() - start) * 1000)
            err = classify(exc) if isinstance(exc, Exception) else QRDriveError("cancelled")
            self.session.add(FileEvent(file_id=self.rec.id, stage=name, ok=False, duration_ms=ms,
                                       message=human(err.kind)["title"]))
            raise
        ms = int((time.perf_counter() - start) * 1000)
        self.rec.durations = {**(self.rec.durations or {}), name: ms}
        self.session.add(FileEvent(file_id=self.rec.id, stage=name, ok=True, duration_ms=ms))


async def choose_storage(session: AsyncSession, rec: FileRecord, avoid: set[int] | None = None) -> Storage:
    avoid = avoid or set()
    candidates: list[int | None] = [rec.storage_id]
    if rec.employee and rec.employee.storage_id:
        candidates.append(rec.employee.storage_id)
    if rec.api_key_id:
        key = await session.get(ApiKey, rec.api_key_id)
        candidates.append(key.storage_id if key else None)
    for sid in candidates:
        if sid and sid not in avoid:
            st = await session.get(Storage, sid)
            if st and st.enabled:
                return st
    primary = (await session.execute(select(Storage).where(Storage.is_primary.is_(True), Storage.enabled.is_(True))
                                     )).scalars().first()
    if primary and primary.id not in avoid:
        return primary
    raise NoStorage()


async def fallback_storage(session: AsyncSession, exclude: int) -> Storage | None:
    return (await session.execute(select(Storage).where(Storage.is_fallback.is_(True), Storage.enabled.is_(True),
                                                        Storage.id != exclude))).scalars().first()


async def _fetch(ctx: Ctx) -> None:
    """downloading: faylni lokal vaqtinchalik papkaga olish, hajm/tur tekshiruvi, sha256."""
    rec, s = ctx.rec, ctx.settings
    if rec.temp_path and Path(rec.temp_path).is_file():
        ctx.local_file = Path(rec.temp_path)
    elif rec.source == "telegram":
        if ctx.tg is None:
            raise TelegramError("Bot tokeni kiritilmagan")
        await ctx.status_msg("downloading")
        dest = spool_path(f"tg{rec.id}")
        ctx.local_file, _ = await ctx.tg.download(rec.tg_file_id, dest)
        ctx.cleanup.append(ctx.local_file)
    elif rec.options.get("source_url"):
        dest = spool_path(f"url{rec.id}")
        max_bytes = int(s.get("max_file_mb") or 100) * 1024 * 1024
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=15), follow_redirects=True) as client:
            async with client.stream("GET", rec.options["source_url"]) as r:
                if r.status_code != 200:
                    raise StorageNotFound(f"source_url HTTP {r.status_code}")
                size = 0
                with open(dest, "wb") as fh:
                    async for chunk in r.aiter_bytes(256 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise FileTooBig(f"{size}")
                        fh.write(chunk)
        rec.temp_path = str(dest)
        ctx.local_file = dest
    else:
        raise StorageNotFound("vaqtinchalik fayl topilmadi")
    rec.size = ctx.local_file.stat().st_size
    if rec.size > int(s.get("max_file_mb") or 100) * 1024 * 1024:
        raise FileTooBig(str(rec.size))
    if not allowed(rec.original_name, s.get("allowed_types", "")):
        raise FileTypeNotAllowed(rec.original_name)
    rec.sha256 = sha256_of(ctx.local_file)


async def _find_duplicate(session: AsyncSession, rec: FileRecord) -> FileRecord | None:
    from .files import visibility_of
    q = select(FileRecord).where(FileRecord.sha256 == rec.sha256, FileRecord.id != rec.id,
                                 FileRecord.link_visibility == visibility_of(rec, await settings_store.load(session)),
                                 FileRecord.status == "delivered", FileRecord.deleted_at.is_(None),
                                 FileRecord.link_url != "")
    if rec.employee_id:
        q = q.where(FileRecord.employee_id == rec.employee_id)
    elif rec.api_key_id:
        q = q.where(FileRecord.api_key_id == rec.api_key_id)
    else:
        return None
    return (await session.execute(q.order_by(FileRecord.id.desc()).limit(1))).scalars().first()


async def _upload(ctx: Ctx, storage: Storage) -> None:
    rec, s = ctx.rec, ctx.settings
    tz = ZoneInfo(s.get("timezone") or config.tz)
    at = (rec.created_at or _now()).astimezone(tz)
    acc = await ctx.session.get(TgAccount, rec.account_id) if rec.account_id else None
    if rec.employee:
        if not rec.employee.folder:  # birinchi faylda papka nomi qotiriladi
            rec.employee.folder = await unique_folder(ctx.session, employee_folder(rec.employee, acc), rec.employee.id)
        folder_name, dept = rec.employee.folder, rec.employee.department
    else:
        folder_name, dept = safe_name(rec.external_user or "API", 64), "API"
    if rec.options.get("folder"):
        folder = join(storage.base_folder, *[safe_name(p, 80) for p in str(rec.options["folder"]).split("/") if p.strip()])
    else:
        folder = render_folder(s.get("folder_template", "{xodim}"), storage.base_folder, folder_name, dept, at)
    filename = render_filename(s.get("filename_template", "{asl_nom}"), rec.original_name, folder_name, at)
    provider = registry.build(storage)
    try:
        await ctx.status_msg("uploading")
        async with ctx.stage("uploading"):
            await provider.ensure_folder(folder)
            remote = await provider.upload(ctx.local_file, folder, filename)
        rec.storage_id, rec.storage = storage.id, storage
        rec.remote_path, rec.remote_id, rec.stored_name = remote.path, remote.id, filename
        await ctx.status_msg("sharing")
        async with ctx.stage("sharing"):
            await create_link(ctx.session, rec, storage, provider, s)
    finally:
        await provider.close()


async def _deliver(ctx: Ctx, duplicate: bool = False) -> None:
    rec, s = ctx.rec, ctx.settings
    async with ctx.stage("qr_generated"):
        caption = qr.caption_for(s.get("qr_style") or {}, rec.original_name, s.get("company_name", ""))
        image = qr.png(rec.link_url, s.get("qr_style"), caption)
    async with ctx.stage("delivered"):
        if rec.source == "telegram" and ctx.tg and rec.tg_chat_id:
            if duplicate:
                text = ctx.text("duplicate") + "\n" + rec.link_url
            else:
                text = ctx.text("done", path=rec.remote_path, url=rec.link_url,
                                vis=ctx.text("vis_private" if rec.link_visibility == "private" else "vis_public"))
                if rec.link_expires_at:
                    tz = ZoneInfo(s.get("timezone") or config.tz)
                    text += "\n" + ctx.text("expires", date=f"{rec.link_expires_at.astimezone(tz):%d.%m.%Y}")
            await ctx.tg.send_photo(rec.tg_chat_id, image, text)
            if rec.tg_status_msg_id:
                await ctx.tg.delete_message(rec.tg_chat_id, rec.tg_status_msg_id)


async def enqueue_webhook(session: AsyncSession, rec: FileRecord, event: str) -> None:
    if not rec.api_key_id:
        return
    key = await session.get(ApiKey, rec.api_key_id)
    if not key or not key.webhook_url or key.revoked:
        return
    payload = {"event": event, "file": serialize(rec)}
    session.add(WebhookDelivery(api_key_id=key.id, event=event, file_id=rec.id,
                                payload=_jsonable(payload), next_attempt_at=_now()))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def process(session: AsyncSession, file_id: int, tg: TelegramClient | None = None) -> FileRecord:
    """Bitta faylni boshidan oxirigacha ishlaydi. Natijani bazaga yozadi."""
    trace_id.set(f"file-{file_id}")
    rec = await session.get(FileRecord, file_id)
    assert rec is not None
    await session.refresh(rec, ["employee", "storage"])
    settings = await settings_store.load(session)
    ctx = Ctx(session, rec, settings)
    own_tg = False
    if rec.source == "telegram" and tg is None and settings.get("bot_token"):
        tg, own_tg = TelegramClient.from_settings(settings), True
    ctx.tg = tg
    if rec.account_id:
        acc = await session.get(TgAccount, rec.account_id)
        if acc:
            ctx.lang = acc.lang or ctx.lang
    try:
        async with ctx.stage("downloading"):
            await _fetch(ctx)
        dup = await _find_duplicate(session, rec) if settings.get("duplicate_policy", "reuse") == "reuse" else None
        if dup:
            rec.duplicate_of, rec.storage_id, rec.storage = dup.duplicate_of or dup.id, dup.storage_id, dup.storage
            rec.remote_path, rec.remote_id, rec.stored_name = dup.remote_path, dup.remote_id, dup.stored_name
            rec.link_url, rec.link_id, rec.link_kind = dup.link_url, dup.link_id, dup.link_kind
            rec.link_expires_at, rec.link_has_password = dup.link_expires_at, dup.link_has_password
            rec.link_visibility = dup.link_visibility
            await _deliver(ctx, duplicate=True)
        else:
            storage = await choose_storage(session, rec)
            if storage.status == "down" and settings.get("auto_fallback"):
                storage = await fallback_storage(session, storage.id) or storage
            try:
                await _upload(ctx, storage)
            except Exception as exc:  # noqa: BLE001
                down = isinstance(classify(exc), StorageUnavailable)
                fb = await fallback_storage(session, storage.id) if down and settings.get("auto_fallback") else None
                if fb is None:
                    raise
                log.warning("asosiy saqlash joyi ishlamayapti — zaxiraga yuklanmoqda", extra={"data": {"storage": fb.name}})
                await _upload(ctx, fb)
            await _deliver(ctx)
        rec.status, rec.error_kind, rec.error_text = "delivered", "", ""
        rec.finished_at, rec.locked_until, rec.next_attempt_at = _now(), None, None
        if rec.temp_path:
            ctx.cleanup.append(Path(rec.temp_path))
            rec.temp_path = ""
        await enqueue_webhook(session, rec, "file.completed")
        await session.commit()
        log.info("fayl tayyor", extra={"data": {"id": rec.id, "durations": rec.durations}})
    except Exception as exc:  # noqa: BLE001
        await _fail(ctx, exc)
    finally:
        for p in ctx.cleanup:
            try:
                if p.is_file() and config.spool_dir in p.resolve().parents:
                    p.unlink()
            except OSError:
                pass
        if own_tg and tg:
            await tg.close()
    return rec


async def _fail(ctx: Ctx, exc: Exception) -> None:
    rec, session = ctx.rec, ctx.session
    err = classify(exc)
    rec.attempts += 1
    rec.error_kind, rec.error_text = err.kind, (err.detail or str(exc))[:2000]
    rec.locked_until = None
    msg = human(err.kind)
    will_retry = err.retry and rec.attempts < MAX_ATTEMPTS
    session.add(FileEvent(file_id=rec.id, stage="retrying" if will_retry else "failed", ok=False,
                          message=f"{msg['title']} ({rec.attempts}/{MAX_ATTEMPTS})"))
    if will_retry:
        delay = RETRY_DELAYS[rec.attempts - 1]
        rec.status, rec.next_attempt_at = "retrying", _now() + timedelta(seconds=delay)
        log.warning("xato, qayta urinish %ss dan keyin", delay, extra={"data": {"id": rec.id, "kind": err.kind}})
        await session.commit()
        await ctx.status_msg("retrying", attempt=rec.attempts, max=MAX_ATTEMPTS - 1)
        return
    rec.status, rec.next_attempt_at, rec.finished_at = "failed", None, _now()
    who = rec.employee.full_name if rec.employee else (rec.external_user or rec.source)
    notify(session, "file_failed", f"Fayl saqlanmadi: {rec.original_name}", f"{who}. {msg['title']}. {msg['hint']}",
           level="error", link=f"/qr/errors?file={rec.id}")
    await enqueue_webhook(session, rec, "file.failed")
    await session.commit()
    log.error("fayl muvaffaqiyatsiz", extra={"data": {"id": rec.id, "kind": err.kind}})
    if rec.source == "telegram":
        rec.temp_path = ""  # Telegram'dan qayta olish mumkin
        await session.commit()
        if ctx.tg and rec.tg_chat_id:
            await ctx.status_msg("failed", reason=msg["title"])


async def retry(session: AsyncSession, rec: FileRecord) -> None:
    rec.status, rec.attempts, rec.next_attempt_at, rec.locked_until = "queued", 0, _now(), None
    rec.error_kind, rec.error_text, rec.finished_at = "", "", None
