"""Panel: bosh sahifa (KPI, grafiklar, «diqqat talab qiladi»), xatolar markazi, jurnal, bildirishnomalar, tizim holati."""
from __future__ import annotations

import csv
import io
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ... import settings_store
from ...core.config import config
from ...core.errors import MESSAGES, human
from ...core.security import Principal
from ...db.models import AuditLog, Employee, FileRecord, Heartbeat, Notification, Storage, TgAccount
from ...db.session import get_session
from ...services import pipeline, system
from ...services.audit import add_audit
from ...services.files import serialize
from ..deps import admin, superadmin, viewer

router = APIRouter(tags=["admin: ops"])


def _utc_day(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), timezone.utc)


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    now = datetime.now(timezone.utc)
    today = _utc_day(now.date())
    live = FileRecord.deleted_at.is_(None)
    delivered = (FileRecord.status == "delivered") & live

    async def count(*conds) -> int:
        return (await session.execute(select(func.count()).select_from(FileRecord).where(*conds))).scalar_one()

    settings = await settings_store.load(session)
    month_ago = now - timedelta(days=30)
    done30 = await count(delivered, FileRecord.created_at >= month_ago)
    failed30 = await count(FileRecord.status == "failed", live, FileRecord.created_at >= month_ago)
    total_size = (await session.execute(select(func.coalesce(func.sum(FileRecord.size), 0)).where(
        delivered, FileRecord.duplicate_of.is_(None)))).scalar_one()
    active_emps = (await session.execute(select(func.count(func.distinct(FileRecord.employee_id))).where(
        FileRecord.created_at >= month_ago, FileRecord.employee_id.isnot(None)))).scalar_one()
    done_rows = (await session.execute(select(FileRecord.created_at, FileRecord.finished_at).where(
        delivered, FileRecord.created_at >= month_ago, FileRecord.finished_at.isnot(None)))).all()
    avg_ms = int(sum((f - c).total_seconds() * 1000 for c, f in done_rows) / len(done_rows)) if done_rows else None
    all_delivered = await count(delivered)

    days = [(today - timedelta(days=i)).date() for i in range(29, -1, -1)]
    rows = (await session.execute(select(func.date(FileRecord.created_at), FileRecord.status, func.count())
                                  .where(live, FileRecord.created_at >= _utc_day(days[0]))
                                  .group_by(func.date(FileRecord.created_at), FileRecord.status))).all()
    per_day: dict[str, dict[str, int]] = {d.isoformat(): {"delivered": 0, "failed": 0} for d in days}
    for d, status, n in rows:
        if str(d) in per_day and status in ("delivered", "failed"):
            per_day[str(d)][status] += n

    storages = (await session.execute(select(Storage).where(Storage.enabled.is_(True)))).scalars().all()
    pending = (await session.execute(select(func.count()).select_from(TgAccount).where(TgAccount.status == "pending"))).scalar_one()
    failed_open = await count(FileRecord.status == "failed", live, FileRecord.created_at >= now - timedelta(days=7))
    expiring = await count(delivered, FileRecord.link_expires_at.isnot(None), FileRecord.link_expires_at > now,
                           FileRecord.link_expires_at < now + timedelta(days=3))
    heartbeats = {h.service: h for h in (await session.execute(select(Heartbeat))).scalars()}

    def alive(name: str) -> bool:
        hb = heartbeats.get(name)
        return bool(hb and now - hb.at < system.HEARTBEAT_STALE)

    return {
        "kpi": {
            "today": await count(delivered, FileRecord.created_at >= today),
            "week": await count(delivered, FileRecord.created_at >= today - timedelta(days=now.weekday())),
            "month": await count(delivered, FileRecord.created_at >= _utc_day(now.date().replace(day=1))),
            "total": all_delivered, "total_size": total_size, "active_employees": active_emps,
            "success_rate": round(done30 / (done30 + failed30), 4) if done30 + failed30 else None,
            "avg_ms": avg_ms, "saved_minutes": all_delivered * int(settings.get("saved_minutes_per_file") or 0),
            "queue": await count(FileRecord.status.in_(("queued", "retrying", "processing")), live),
        },
        "daily": [{"date": d, **v} for d, v in per_day.items()],
        "storages": [{"id": s.id, "name": s.name, "status": s.status, "used": s.quota_used, "total": s.quota_total,
                      "is_primary": s.is_primary} for s in storages],
        "attention": {
            "pending_requests": pending, "failed_files": failed_open, "links_expiring": expiring,
            "storages_down": [s.name for s in storages if s.status == "down"],
            "quota_high": [s.name for s in storages if s.quota_total and s.quota_used and s.quota_used / s.quota_total > 0.9],
            "no_storage": not any(s.is_primary for s in storages),
            "worker_down": not alive("worker"), "bot_down": bool(settings.get("bot_token")) and not alive("bot"),
        },
        "setup_done": bool(settings.get("setup_done")),
        "bot_username": settings.get("bot_username", ""),
    }


# ---------------- xatolar markazi ----------------
@router.get("/errors")
async def errors(days: int = 30, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(select(FileRecord).where(
        FileRecord.status.in_(("failed", "retrying")), FileRecord.deleted_at.is_(None), FileRecord.created_at >= since)
        .order_by(FileRecord.id.desc()).limit(1000))).scalars().all()
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        kind = r.error_kind or "unknown"
        g = groups.setdefault(kind, {**human(kind), "count": 0, "items": []})
        g["count"] += 1
        g["items"].append(serialize(r))
    return {"groups": sorted(groups.values(), key=lambda g: -g["count"]), "total": len(rows)}


class RetryBody(BaseModel):
    ids: list[int] | None = None
    kind: str | None = None


@router.post("/errors/retry")
async def retry_errors(body: RetryBody, session: AsyncSession = Depends(get_session), user: Principal = Depends(admin)):
    q = select(FileRecord).where(FileRecord.status == "failed", FileRecord.deleted_at.is_(None))
    if body.ids:
        q = q.where(FileRecord.id.in_(body.ids))
    if body.kind:
        q = q.where(FileRecord.error_kind == body.kind)
    n = 0
    for rec in (await session.execute(q)).scalars():
        await pipeline.retry(session, rec)
        n += 1
    add_audit(session, "file.retry_bulk", actor=user.username, details={"count": n, "kind": body.kind})
    await session.commit()
    return {"retried": n}


@router.get("/errors/kinds")
async def error_kinds(_: Principal = Depends(viewer)):
    return MESSAGES


# ---------------- jurnal ----------------
def _audit_query(q: str, actor_kind: str, action: str, date_from: date | None, date_to: date | None):
    query = select(AuditLog)
    if q:
        like = f"%{q}%"
        query = query.where(or_(AuditLog.actor.ilike(like), AuditLog.target.ilike(like), AuditLog.action.ilike(like)))
    if actor_kind:
        query = query.where(AuditLog.actor_kind == actor_kind)
    if action:
        query = query.where(AuditLog.action.startswith(action))
    if date_from:
        query = query.where(AuditLog.at >= _utc_day(date_from))
    if date_to:
        query = query.where(AuditLog.at < _utc_day(date_to + timedelta(days=1)))
    return query


@router.get("/audit")
async def audit(q: str = "", actor_kind: str = "", action: str = "", date_from: date | None = None, date_to: date | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(100, le=500),
                session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    query = _audit_query(q, actor_kind, action, date_from, date_to)
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await session.execute(query.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars()
    return {"items": [{"id": a.id, "at": a.at, "actor": a.actor, "actor_kind": a.actor_kind, "action": a.action,
                       "target": a.target, "details": a.details} for a in rows], "total": total}


@router.get("/audit/export.csv")
async def audit_export(q: str = "", actor_kind: str = "", action: str = "", date_from: date | None = None,
                       date_to: date | None = None, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    rows = (await session.execute(_audit_query(q, actor_kind, action, date_from, date_to)
                                  .order_by(AuditLog.id.desc()).limit(100000))).scalars()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Vaqt (UTC)", "Kim", "Turi", "Amal", "Obyekt", "Tafsilot"])
    for a in rows:
        w.writerow([a.at.isoformat(), a.actor, a.actor_kind, a.action, a.target, a.details])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=qrdrive-jurnal.csv"})


# ---------------- bildirishnomalar ----------------
@router.get("/notifications")
async def notifications(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    panel = Notification.audience != "bot"  # «bot» — faqat bot adminlari uchun (masalan har bir yangi fayl)
    rows = (await session.execute(select(Notification).where(panel).order_by(Notification.id.desc()).limit(50))).scalars()
    unread = (await session.execute(select(func.count()).select_from(Notification).where(
        Notification.read.is_(False), panel))).scalar_one()
    pending = (await session.execute(select(func.count()).select_from(TgAccount).where(TgAccount.status == "pending"))).scalar_one()
    failed = (await session.execute(select(func.count()).select_from(FileRecord).where(
        FileRecord.status == "failed", FileRecord.deleted_at.is_(None)))).scalar_one()
    return {"unread": unread, "pending_requests": pending, "failed_files": failed,
            "items": [{"id": n.id, "at": n.at, "kind": n.kind, "level": n.level, "title": n.title, "body": n.body,
                       "link": n.link, "read": n.read} for n in rows]}


class ReadBody(BaseModel):
    ids: list[int] | None = None


@router.post("/notifications/read")
async def mark_read(body: ReadBody, session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    q = update(Notification).values(read=True)
    if body.ids:
        q = q.where(Notification.id.in_(body.ids))
    await session.execute(q)
    await session.commit()
    return {"ok": True}


# ---------------- tizim holati ----------------
@router.get("/system")
async def system_status(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    now = datetime.now(timezone.utc)
    hbs = {h.service: h for h in (await session.execute(select(Heartbeat))).scalars()}
    services = []
    for name, label in (("api", "API va panel"), ("worker", "Fon ishlovchi (worker)"), ("bot", "Telegram bot")):
        hb = hbs.get(name)
        ok = name == "api" or bool(hb and now - hb.at < system.HEARTBEAT_STALE)
        services.append({"name": name, "label": label, "ok": ok, "last_seen": hb.at if hb else None,
                         "started_at": hb.started_at if hb else None, "info": hb.info if hb else {}})
    queue = dict((await session.execute(select(FileRecord.status, func.count()).where(
        FileRecord.status.in_(("queued", "retrying", "processing")), FileRecord.deleted_at.is_(None))
        .group_by(FileRecord.status))).all())
    db_size = sum(os.path.getsize(p) for p in (config.db_path, config.db_path + "-wal") if os.path.exists(p))
    disk = shutil.disk_usage(config.data_dir)
    storages = (await session.execute(select(Storage))).scalars().all()
    settings = await settings_store.load(session)
    return {
        "version": system.VERSION, "services": services, "queue": queue,
        "database": {"size": db_size, "path": "qrdrive.sqlite3"},
        "disk": {"free": disk.free, "total": disk.total},
        "telegram_api": {"mode": "lokal server" if settings.get("bot_api_url") else "rasmiy (20 MB gacha yuklab olish)",
                         "bot": settings.get("bot_username", "")},
        "storages": [{"id": s.id, "name": s.name, "status": s.status, "latency_ms": s.latency_ms,
                      "last_check_at": s.last_check_at, "error": human(s.last_error)["title"] if s.last_error else "",
                      "error_kind": s.last_error}
                     for s in storages],
        "backups": system.list_backups()[:20],
        # Faqat ko'rish uchun: bular ishga tushirish parametrlari (/etc/zona/qrdrive.env). Qolgan hammasi — panelda.
        "runtime": {"port": config.port, "host": config.host, "data_dir": str(config.data_dir), "debug": config.debug,
                    "public_base_url": settings_store.public_base(settings), "timezone": settings.get("timezone") or config.tz,
                    "master_key_set": config.master_key != "dev-only-change-me", "sso_set": config.sso_secret != "dev-only-change-me"},
    }


@router.post("/system/backup")
async def make_backup(session: AsyncSession = Depends(get_session), user: Principal = Depends(superadmin)):
    settings = await settings_store.load(session)
    path = await system.create_backup(int(settings.get("backup_keep_days") or 14))
    add_audit(session, "system.backup", actor=user.username, target=path.name)
    await session.commit()
    return {"name": path.name, "size": path.stat().st_size}


@router.get("/system/backups/{name}")
async def download_backup(name: str, _: Principal = Depends(superadmin)):
    path = config.backups_dir / name
    if not name.startswith("qrdrive-") or "/" in name or "\\" in name or not path.is_file():
        raise HTTPException(404, "Zaxira topilmadi")
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.post("/system/legacy-import")
async def legacy_import(file: UploadFile = File(...), session: AsyncSession = Depends(get_session),
                        user: Principal = Depends(superadmin)):
    """Eski kadrlar-bot .env faylini yuklash: token, Synology, ruxsat berilgan ID'lar, limitlar ko'chiriladi."""
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    env = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.split(" #", 1)[0].strip().strip('"').strip("'")
    if not await system.import_legacy(session, env):
        raise HTTPException(400, "Faylda BOT_TOKEN yoki SYNO_URL topilmadi — bu eski bot .env fayli emas")
    add_audit(session, "system.legacy_import_ui", actor=user.username, details={"keys": sorted(k for k in env if not k.endswith(("TOKEN", "PASS", "PASSWORD", "HASH")))})
    await session.commit()
    return {"ok": True, "employees": len(settings_store.parse_ids(env.get("ALLOWED_USER_IDS", ""))), "storage": bool(env.get("SYNO_URL"))}


@router.get("/departments")
async def departments(session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    rows = (await session.execute(select(Employee.department).where(Employee.department != "").distinct())).scalars()
    return sorted(rows)
