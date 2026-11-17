"""Tizim: bazani tayyorlash, eski kadrlar-bot .env importi, heartbeat, zaxira nusxa."""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import settings_store
from ..core.config import config
from ..db.models import Employee, Heartbeat, Setting, Storage, TgAccount
from ..db.session import init_db, session_scope
from ..storage import registry
from .audit import add_audit

log = logging.getLogger("qrdrive.system")
VERSION = "0.1.0"


def _read_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.split(" #", 1)[0].strip().strip('"').strip("'")
    return out


async def import_legacy(session: AsyncSession, env: dict[str, str]) -> bool:
    """Eski bot .env qiymatlarini sozlamalarga ko'chiradi (faqat baza bo'sh bo'lsa)."""
    if not env.get("BOT_TOKEN") and not env.get("SYNO_URL"):
        return False
    values: dict[str, Any] = {}
    if env.get("BOT_TOKEN"):
        values["bot_token"] = env["BOT_TOKEN"]
    if env.get("TELEGRAM_API_URL"):
        values.update(bot_api_url=env["TELEGRAM_API_URL"], bot_api_local=True)
    if env.get("MAX_FILE_MB", "").isdigit():
        values["max_file_mb"] = int(env["MAX_FILE_MB"])
    if env.get("SHARE_EXPIRE_DAYS", "").isdigit():
        values["link_expire_days"] = int(env["SHARE_EXPIRE_DAYS"])
    if env.get("SHARE_PASSWORD"):
        values["link_password"] = env["SHARE_PASSWORD"]
    await settings_store.save(session, values)
    if env.get("SYNO_URL"):
        primary = not (await session.execute(select(Storage).where(Storage.is_primary.is_(True)))).first()
        st = Storage(name="Synology (eski bot)", kind="synology", base_folder="/" + env.get("SYNO_BASE_FOLDER", "/Kadrlar").strip("/"),
                     is_primary=primary)
        registry.set_config(st, {"url": env["SYNO_URL"], "username": env.get("SYNO_USER", ""),
                                 "password": env.get("SYNO_PASS", ""),
                                 "verify_ssl": env.get("SYNO_VERIFY_SSL", "true").lower() in ("1", "true", "yes")})
        session.add(st)
    # Ruxsat berilgan ID'lar: har biri uchun xodim. Papka nomi birinchi faylda username'dan olinadi (eski bot kabi)
    for tid in settings_store.parse_ids(env.get("ALLOWED_USER_IDS", "")):
        if (await session.execute(select(TgAccount).where(TgAccount.telegram_id == tid))).scalar_one_or_none():
            continue
        emp = Employee(full_name=f"Xodim {tid}", note="Eski botdan import qilingan. Ma'lumotlarini to'ldiring.")
        session.add(emp)
        await session.flush()
        session.add(TgAccount(telegram_id=tid, employee_id=emp.id, status="active"))
    add_audit(session, "system.legacy_import", actor="system", actor_kind="system",
              details={"keys": sorted(values), "storage": bool(env.get("SYNO_URL"))})
    await session.commit()
    log.info("eski .env sozlamalari import qilindi")
    return True


# Standart saqlash joyi: StarGroup NAS (Synology Drive papkasi). Login/parol panelda kiritiladi.
DEFAULT_STORAGE = {
    "name": "StarGroup NAS (file.stargroup.uz)",
    "kind": "synology",
    "config": {"url": "https://file.stargroup.uz", "drive_folder": "https://file.stargroup.uz/#file_id=984701843502314054",
               "verify_ssl": True},
}


async def seed_default_storage(session: AsyncSession) -> None:
    if not config.seed_default_storage or (await session.execute(select(func.count()).select_from(Storage))).scalar_one():
        return
    st = Storage(name=DEFAULT_STORAGE["name"], kind=DEFAULT_STORAGE["kind"], base_folder="/", is_primary=True, status="unknown",
                 link_mode="provider",
                 last_error="not_configured")
    registry.set_config(st, DEFAULT_STORAGE["config"])
    session.add(st)
    add_audit(session, "storage.default_seeded", actor="system", actor_kind="system", target=st.name)
    await session.commit()


async def bootstrap() -> None:
    config.ensure_dirs()
    await init_db()
    async with session_scope() as s:
        has_settings = (await s.execute(select(func.count()).select_from(Setting))).scalar_one()
        has_storage = (await s.execute(select(func.count()).select_from(Storage))).scalar_one()
        if not has_settings and not has_storage:
            env = _read_env_file(config.legacy_env) if config.legacy_env else {}
            if not env and os.environ.get("BOT_TOKEN"):
                env = {k: v for k, v in os.environ.items() if k.isupper()}
            if env:
                await import_legacy(s, env)
            await seed_default_storage(s)


async def beat(service: str, info: dict[str, Any] | None = None, started: datetime | None = None) -> None:
    async with session_scope() as s:
        hb = await s.get(Heartbeat, service)
        now = datetime.now(timezone.utc)
        if hb is None:
            hb = Heartbeat(service=service, started_at=started or now)
            s.add(hb)
        if started:
            hb.started_at = started
        hb.at, hb.info = now, {**(info or {}), "pid": os.getpid(), "version": VERSION}
        await s.commit()


def _backup_sync(dest: Path) -> None:
    src = sqlite3.connect(config.db_path)
    dst = sqlite3.connect(dest)
    try:
        with dst:
            src.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"integrity_check: {ok}")
    finally:
        src.close()
        dst.close()


async def create_backup(keep_days: int = 14) -> Path:
    config.backups_dir.mkdir(parents=True, exist_ok=True)
    dest = config.backups_dir / f"qrdrive-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    await asyncio.to_thread(_backup_sync, dest)
    cutoff = time.time() - keep_days * 86400
    for old in config.backups_dir.glob("qrdrive-*.sqlite3"):
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    return dest


def list_backups() -> list[dict[str, Any]]:
    if not config.backups_dir.is_dir():
        return []
    items = sorted(config.backups_dir.glob("qrdrive-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "size": p.stat().st_size,
             "created_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)} for p in items]


HEARTBEAT_STALE = timedelta(seconds=90)
