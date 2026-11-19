"""Fayl jarayoni: received → downloading → uploading → sharing → qr_generated → delivered (yoki failed).
Har bosqich FileEvent sifatida vaqti bilan yoziladi. Xatoda 3 marta qayta urinish (10 s, 60 s, 5 daq)."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import settings_store
from ..core.config import config
from ..core.errors import (FileTooBig, FileTypeNotAllowed, NoStorage, QRDriveError, StorageNotFound,
                           StorageUnavailable, TelegramError, classify, human)
from ..core.logging import trace_id
from ..db.models import ApiKey, FileEvent, FileRecord, Storage, SystemLink, TgAccount, WebhookDelivery
from ..storage import registry
from ..storage.base import RemoteFile, join
from . import admins, archive, qr
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


async def claim_prefetch(session: AsyncSession) -> int | None:
    """Tugma bosilishini kutayotgan Telegram faylini oldindan yuklab olish uchun band qiladi."""
    now = _now()
    cond = and_(FileRecord.status == "awaiting", FileRecord.source == "telegram", FileRecord.temp_path == "",
                FileRecord.tg_file_id != "", or_(FileRecord.locked_until.is_(None), FileRecord.locked_until < now))
    fid = (await session.execute(select(FileRecord.id).where(cond).order_by(FileRecord.id).limit(1))).scalar_one_or_none()
    if fid is None:
        return None
    res = await session.execute(update(FileRecord).where(FileRecord.id == fid, cond)
                                .values(locked_until=now + timedelta(minutes=10)))
    await session.commit()
    return fid if res.rowcount else None


async def prefetch(session: AsyncSession, file_id: int) -> None:
    """Telegram'dan oldindan yuklab olish — foydalanuvchi tugmani bosguncha fayl tayyor turadi (tezlik).
    Faqat temp_path/hajm ustunlari yangilanadi: bot shu paytda holatni o'zgartirishi mumkin."""
    rec = await session.get(FileRecord, file_id)
    settings = await settings_store.load(session)
    if rec is None or not settings.get("bot_token"):
        return
    dest = spool_path(f"tg{rec.id}")
    try:
        async with TelegramClient.from_settings(settings) as tg:
            await tg.download(rec.tg_file_id, dest)
        values: dict[str, Any] = {"temp_path": str(dest), "size": dest.stat().st_size, "locked_until": None}
    except Exception as exc:  # noqa: BLE001 — asosiy jarayon keyin qayta urinadi
        dest.unlink(missing_ok=True)
        log.warning("oldindan yuklab olinmadi", extra={"data": {"id": file_id, "error": type(exc).__name__}})
        values = {"locked_until": _now() + timedelta(minutes=5)}
    await session.execute(update(FileRecord).where(FileRecord.id == file_id).values(**values))
    await session.commit()


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
        self.cleanup_dirs: list[Path] = []
        self.bg: set[asyncio.Task] = set()
        self.prepared: archive.Extracted | None = None  # bir nechta fayldan yig'ilgan papka
        self.mode = "new"  # new | duplicate | replaced | unchanged | folder

    def text(self, key: str, **kw: Any) -> str:
        return settings_store.text(self.settings, self.lang, key, **kw)

    async def status_msg(self, key: str, **kw: Any) -> None:
        """Telegram'dagi holat xabari fonda yangilanadi — fayl jarayoni Telegram javobini kutmaydi (tezlik)."""
        if self.tg and self.rec.tg_chat_id and self.rec.tg_status_msg_id:
            task = asyncio.create_task(self.tg.edit_message(self.rec.tg_chat_id, self.rec.tg_status_msg_id, self.text(key, **kw)))
            self.bg.add(task)
            task.add_done_callback(self.bg.discard)

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
                                 FileRecord.replaced_by.is_(None), FileRecord.link_url != "",
                                 FileRecord.kind == ("folder" if rec.options.get("archive") == "folder" else "file"))
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
    async with registry.use(storage) as provider:
        await ctx.status_msg("uploading")
        async with ctx.stage("uploading"):
            if rec.options.get("archive") == "folder" or ctx.prepared is not None:
                # papka nomi: shablon bo'yicha, arxiv kengaytmasisiz (masalan «Hujjatlar_2026-11-17_18-30-00»)
                dir_name = safe_name(render_filename(s.get("filename_template", "{asl_nom}"), archive.stem(rec.original_name) + ".x",
                                                     folder_name, at)[:-2])
                dir_name = await _free_name(ctx.session, storage.id, folder, dir_name)
                remote = await _upload_tree(ctx, provider, join(folder, dir_name))
                filename = dir_name
            else:
                # yangi fayl hech qachon boshqa faylning ustidan yozmasin (bir xil nom, bir soniya ichida)
                filename = await _free_name(ctx.session, storage.id, folder, filename)
                await provider.ensure_folder(folder)
                remote = await provider.upload(ctx.local_file, folder, filename)
        rec.storage_id, rec.storage = storage.id, storage
        rec.remote_path, rec.remote_id, rec.stored_name = remote.path, remote.id, filename
        await ctx.status_msg("sharing")
        async with ctx.stage("sharing"):
            await create_link(ctx.session, rec, storage, provider, s)


async def _free_name(session: AsyncSession, storage_id: int, folder: str, name: str) -> str:
    """Shu papkada tizimdagi boshqa fayl egallagan nom bo'lsa — «nom_2.ext», «nom_3.ext», ..."""
    stem_, dot, ext = name.rpartition(".")
    if not dot or not stem_:
        stem_, ext = name, ""
    candidate, n = name, 2
    while (await session.execute(select(FileRecord.id).where(
            FileRecord.storage_id == storage_id, FileRecord.remote_path == join(folder, candidate),
            FileRecord.deleted_at.is_(None)).limit(1))).first():
        candidate = f"{stem_}_{n}.{ext}" if ext else f"{stem_}_{n}"
        n += 1
    return candidate


UPLOAD_PARALLEL = 4


async def _upload_tree(ctx: Ctx, provider, target: str) -> RemoteFile:
    """Arxivni ochib (yoki guruhdagi fayllarni) papka tuzilmasi bilan parallel yuklaydi. Natija — papka (bitta havola)."""
    s = ctx.settings
    ex = ctx.prepared
    if ex is None:
        max_mb = int(s.get("archive_max_mb") or 2048)
        dest = spool_path(f"x{ctx.rec.id}")
        ctx.cleanup_dirs.append(dest)
        ex = await asyncio.to_thread(archive.extract, ctx.local_file, dest, max_files=int(s.get("archive_max_files") or 1000),
                                     max_bytes=max_mb * 1024 * 1024, allowed=lambda n: allowed(n, s.get("allowed_types", "")))
    dirs = sorted({target} | {join(target, rel.rsplit("/", 1)[0]) for rel, _ in ex.files if "/" in rel}, key=len)
    for d in dirs:  # papkalar ketma-ket (ba'zi provayderlarda parallel yaratish dublikat beradi)
        await provider.ensure_folder(d)
    sem = asyncio.Semaphore(UPLOAD_PARALLEL)

    async def one(rel: str) -> None:
        async with sem:
            parent, _, name = rel.rpartition("/")
            await provider.upload(ex.root / rel, join(target, parent) if parent else target, name)

    await asyncio.gather(*(one(rel) for rel, _ in ex.files))
    ctx.rec.kind = "folder"
    ctx.rec.items = [{"name": rel, "size": size} for rel, size in ex.files]
    ctx.rec.size = sum(size for _, size in ex.files)
    ctx.mode = "folder"
    return RemoteFile(path=target, id=target, is_dir=True)


async def _fetch_batch(ctx: Ctx) -> archive.Extracted:
    """Birdaniga yuborilgan fayllarni bitta papkaga yig'adi (oldindan yuklab olinganlari darhol, qolganlari parallel)."""
    rec, s, session = ctx.rec, ctx.settings, ctx.session
    ids = [int(i) for i in rec.options.get("batch_children") or []]
    children = [c for c in [await session.get(FileRecord, i) for i in ids] if c is not None]
    dest = spool_path(f"b{rec.id}")
    dest.mkdir(parents=True, exist_ok=True)
    ctx.cleanup_dirs.append(dest)
    max_bytes = int(s.get("max_file_mb") or 100) * 1024 * 1024
    sem = asyncio.Semaphore(4)

    async def local(child: FileRecord) -> Path:
        if child.temp_path and Path(child.temp_path).is_file():
            return Path(child.temp_path)
        if ctx.tg is None:
            raise TelegramError("Bot tokeni kiritilmagan")
        async with sem:
            path, _ = await ctx.tg.download(child.tg_file_id, spool_path(f"tg{child.id}"))
            return path

    paths = await asyncio.gather(*(local(c) for c in children))
    used: set[str] = set()
    files: list[tuple[str, int]] = []
    for child, path in zip(children, paths):
        name = safe_name(child.original_name)
        stem_, dot, ext = name.rpartition(".")
        base, n = (stem_, f".{ext}") if dot and stem_ else (name, ""), 2
        while name.lower() in used:  # bir xil nomli fayllar: «nom_2.pdf»
            name = f"{base[0]}_{n}{base[1]}"
            n += 1
        used.add(name.lower())
        size = path.stat().st_size
        if size > max_bytes:
            raise FileTooBig(str(size))
        shutil.move(str(path), dest / name)
        files.append((name, size))
    rec.size = sum(sz for _, sz in files)
    return archive.Extracted(root=dest, files=sorted(files))


async def _replace(ctx: Ctx, prev: FileRecord) -> None:
    """Eski faylni yangisi bilan almashtirish: o'sha joyga ustidan yoziladi — havola va QR o'zgarmaydi."""
    rec, session = ctx.rec, ctx.session
    storage = prev.storage
    folder, _, name = prev.remote_path.rpartition("/")
    async with registry.use(storage) as provider:
        await ctx.status_msg("uploading")
        async with ctx.stage("uploading"):
            if hasattr(provider, "replace"):
                remote = await provider.replace(ctx.local_file, RemoteFile(path=prev.remote_path, id=prev.remote_id))
            else:
                remote = await provider.upload(ctx.local_file, folder or "/", name)
    rec.storage_id, rec.storage = storage.id, storage
    rec.remote_path, rec.remote_id, rec.stored_name = prev.remote_path, remote.id or prev.remote_id, prev.stored_name
    rec.link_url, rec.link_id, rec.link_kind = prev.link_url, prev.link_id, prev.link_kind
    rec.link_expires_at, rec.link_has_password, rec.link_visibility = prev.link_expires_at, prev.link_has_password, prev.link_visibility
    if prev.link_kind == "system" and prev.link_id:  # tizim havolasi endi yangi versiyaga ishora qiladi
        await session.execute(update(SystemLink).where(SystemLink.file_id == prev.id).values(file_id=rec.id))
    rec.version, prev.replaced_by = (prev.version or 1) + 1, rec.id
    session.add(FileEvent(file_id=rec.id, stage="sharing", ok=True, message=f"v{rec.version}: havola o'zgarmadi"))
    ctx.mode = "replaced"


async def _replace_target(session: AsyncSession, rec: FileRecord) -> FileRecord | None:
    pid = rec.options.get("replace_of")
    if not pid:
        return None
    prev = await session.get(FileRecord, int(pid))
    if prev is None or prev.status != "delivered" or prev.deleted_at or prev.replaced_by or prev.kind != "file" or not prev.storage:
        return None
    await session.refresh(prev, ["storage"])
    return prev


async def _deliver(ctx: Ctx, duplicate: bool = False) -> None:
    rec, s = ctx.rec, ctx.settings
    async with ctx.stage("qr_generated"):
        caption = qr.caption_for(s.get("qr_style") or {}, rec.original_name, s.get("company_name", ""))
        image = qr.png(rec.link_url, s.get("qr_style"), caption)
    async with ctx.stage("delivered"):
        if rec.source == "telegram" and ctx.tg and rec.tg_chat_id:
            if ctx.mode == "replaced":
                text = ctx.text("replaced_done", version=rec.version, path=rec.remote_path, url=rec.link_url)
            elif ctx.mode == "unchanged":
                text = ctx.text("unchanged") + "\n" + rec.link_url
            elif duplicate:
                text = ctx.text("duplicate") + "\n" + rec.link_url
            elif ctx.mode == "folder":
                text = ctx.text("folder_done", count=len(rec.items or []), path=rec.remote_path, url=rec.link_url,
                                vis=ctx.text("vis_private" if rec.link_visibility == "private" else "vis_public"))
            else:
                text = ctx.text("done", path=rec.remote_path, url=rec.link_url,
                                vis=ctx.text("vis_private" if rec.link_visibility == "private" else "vis_public"))
                if rec.link_expires_at:
                    tz = ZoneInfo(s.get("timezone") or config.tz)
                    text += "\n" + ctx.text("expires", date=f"{rec.link_expires_at.astimezone(tz):%d.%m.%Y}")
            await ctx.tg.send_photo(rec.tg_chat_id, image, text, reply_to=(rec.options or {}).get("tg_msg_id"))
            if rec.tg_status_msg_id:
                await ctx.tg.delete_message(rec.tg_chat_id, rec.tg_status_msg_id)


def _size(n: int | None) -> str:
    n = n or 0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


async def _admin_notice(ctx: Ctx, duplicate: bool) -> None:
    """Bot adminlariga: kim, qaysi fayl, qayerga saqlandi va havolasi (adminning o'z fayli bundan mustasno)."""
    rec = ctx.rec
    if rec.account_id:
        acc = await ctx.session.get(TgAccount, rec.account_id)
        if admins.is_admin(acc, ctx.settings):
            return
    who = rec.employee.full_name if rec.employee else (rec.external_user or rec.actor or rec.source)
    label = {"replaced": "♻️ Fayl yangilandi", "unchanged": "ℹ️ O'zgarmagan fayl qayta yuborildi",
             "folder": "📂 Yangi papka"}.get(ctx.mode, "ℹ️ Takroriy fayl" if duplicate else "📄 Yangi fayl")
    lines = [f"👤 {who}" + (f" · {rec.source}" if rec.source != "telegram" else "")]
    if ctx.mode == "folder":
        lines.append(f"{len(rec.items or [])} ta fayl · {_size(rec.size or sum(int(i.get('size') or 0) for i in rec.items or []))}")
    else:
        lines.append(_size(rec.size) + (f" · v{rec.version}" if ctx.mode == "replaced" else ""))
    lines += [f"📁 {rec.remote_path}", ("🔒 " if rec.link_visibility == "private" else "🌐 ") + (rec.link_url or "")]
    if rec.caption:
        lines.append(f"💬 {rec.caption[:200]}")
    notify(ctx.session, "file_replaced" if ctx.mode == "replaced" else "file_delivered", f"{label}: {rec.original_name}",
           "\n".join(lines), level="success", link=f"/qr/files?file={rec.id}", audience="bot", data={"file_id": rec.id})


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
        batch = bool(rec.options.get("batch_children"))
        async with ctx.stage("downloading"):
            if batch:
                ctx.prepared = await _fetch_batch(ctx)
            else:
                await _fetch(ctx)
        prev = None if batch else await _replace_target(session, rec)
        dup = None
        if prev is not None and prev.sha256 == rec.sha256:  # tarkib o'zgarmagan — eski QR
            dup, ctx.mode = prev, "unchanged"
        elif prev is None and not batch and settings.get("duplicate_policy", "reuse") == "reuse":
            dup = await _find_duplicate(session, rec)
        if prev is not None and dup is None:
            await _replace(ctx, prev)
            await _deliver(ctx)
        elif dup:
            rec.duplicate_of, rec.storage_id, rec.storage = dup.duplicate_of or dup.id, dup.storage_id, dup.storage
            rec.remote_path, rec.remote_id, rec.stored_name = dup.remote_path, dup.remote_id, dup.stored_name
            rec.link_url, rec.link_id, rec.link_kind = dup.link_url, dup.link_id, dup.link_kind
            rec.link_expires_at, rec.link_has_password = dup.link_expires_at, dup.link_has_password
            rec.link_visibility = dup.link_visibility
            rec.kind, rec.items = dup.kind, dup.items
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
        if batch:  # guruhdagi alohida yozuvlar endi papka ichida — ro'yxatdan olib tashlanadi
            await session.execute(delete(FileRecord).where(FileRecord.id.in_([int(i) for i in rec.options["batch_children"]]),
                                                           FileRecord.status == "merged"))
        rec.status, rec.error_kind, rec.error_text = "delivered", "", ""
        rec.finished_at, rec.locked_until, rec.next_attempt_at = _now(), None, None
        await _admin_notice(ctx, duplicate=dup is not None)
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
        for d in ctx.cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)
        if ctx.bg:  # fondagi Telegram xabarlari tugashini qisqa kutamiz
            await asyncio.wait(ctx.bg, timeout=5)
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
