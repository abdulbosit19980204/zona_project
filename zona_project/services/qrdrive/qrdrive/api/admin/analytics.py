"""Panel: analitika — sana oralig'i bo'yicha yuklashlar, reytinglar, fayl turlari, hajm, faollik xaritasi,
saqlash joylari, xatolar, bosqichlar davomiyligi, API kalitlar. Excel eksport."""
from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import settings_store
from ...core.errors import human
from ...core.security import Principal
from ...db.models import ApiKey, ApiRequest, FileRecord
from ...db.session import get_session
from ..deps import viewer

router = APIRouter(prefix="/analytics", tags=["admin: analytics"])

SIZE_BUCKETS = [(1024 * 1024, "< 1 MB"), (10 * 1024 * 1024, "1–10 MB"), (50 * 1024 * 1024, "10–50 MB"),
                (100 * 1024 * 1024, "50–100 MB"), (None, "> 100 MB")]
STAGES = ["downloading", "uploading", "sharing", "qr_generated", "delivered"]


def _type(mime: str, name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if not mime or mime == "application/octet-stream":
        import mimetypes
        mime = mimetypes.guess_type(name)[0] or ""
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime == "application/pdf" or ext == "pdf":
        return "pdf"
    if ext in ("doc", "docx", "odt", "rtf", "txt"):
        return "doc"
    if ext in ("xls", "xlsx", "ods", "csv"):
        return "sheet"
    if ext in ("zip", "rar", "7z", "gz"):
        return "archive"
    return "other"


async def compute(session: AsyncSession, date_from: date | None, date_to: date | None) -> dict[str, Any]:
    settings = await settings_store.load(session)
    tz = ZoneInfo(settings.get("timezone") or "Asia/Tashkent")
    today = datetime.now(tz).date()
    d_to = date_to or today
    d_from = date_from or (d_to - timedelta(days=29))
    start = datetime.combine(d_from, datetime.min.time(), tz).astimezone(timezone.utc)
    end = datetime.combine(d_to + timedelta(days=1), datetime.min.time(), tz).astimezone(timezone.utc)
    rows = (await session.execute(select(FileRecord).where(
        FileRecord.created_at >= start, FileRecord.created_at < end, FileRecord.deleted_at.is_(None)))).scalars().all()

    days = [(d_from + timedelta(days=i)).isoformat() for i in range((d_to - d_from).days + 1)]
    daily = {d: {"date": d, "delivered": 0, "failed": 0, "size": 0} for d in days}
    by_emp: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "size": 0})
    by_dept: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "size": 0})
    types: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    heat = [[0] * 24 for _ in range(7)]
    storages: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "size": 0})
    errors: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    stage_sum: dict[str, list[int]] = defaultdict(list)
    proc: list[float] = []

    for r in rows:
        local = r.created_at.astimezone(tz)
        key = local.date().isoformat()
        if r.status == "failed":
            errors[r.error_kind or "unknown"] += 1
            if key in daily:
                daily[key]["failed"] += 1
            continue
        if r.status != "delivered":
            continue
        size = r.size or 0
        if key in daily:
            daily[key]["delivered"] += 1
            daily[key]["size"] += size
        name = r.employee.full_name if r.employee else (r.external_user or "API")
        dept = (r.employee.department if r.employee else "") or "—"
        for bucket, k in ((by_emp, name), (by_dept, dept)):
            bucket[k]["count"] += 1
            bucket[k]["size"] += size
        types[_type(r.mime or "", r.original_name)] += 1
        for limit, label in SIZE_BUCKETS:
            if limit is None or size < limit:
                sizes[label] += 1
                break
        heat[local.weekday()][local.hour] += 1
        sname = r.storage.name if r.storage else "—"
        storages[sname]["count"] += 1
        storages[sname]["size"] += 0 if r.duplicate_of else size
        sources[r.source] += 1
        for st in STAGES:
            if st in (r.durations or {}):
                stage_sum[st].append(int(r.durations[st]))
        if r.finished_at:
            proc.append((r.finished_at - r.created_at).total_seconds() * 1000)

    api_rows = (await session.execute(select(ApiRequest.api_key_id, func.count(), func.avg(ApiRequest.duration_ms),
                                             func.sum(case((ApiRequest.status_code >= 400, 1), else_=0)))
                                      .where(ApiRequest.at >= start, ApiRequest.at < end)
                                      .group_by(ApiRequest.api_key_id))).all()
    names = {k.id: k.name for k in (await session.execute(select(ApiKey))).scalars()}
    delivered = sum(d["delivered"] for d in daily.values())
    failed = sum(errors.values())

    def top(d: dict[str, dict[str, Any]], n: int = 15) -> list[dict[str, Any]]:
        return [{"name": k, **v} for k, v in sorted(d.items(), key=lambda kv: -kv[1]["count"])[:n]]

    return {
        "range": {"from": d_from.isoformat(), "to": d_to.isoformat()},
        "totals": {"delivered": delivered, "failed": failed, "size": sum(d["size"] for d in daily.values()),
                   "employees": len(by_emp), "success_rate": round(delivered / (delivered + failed), 4) if delivered + failed else None,
                   "avg_ms": int(sum(proc) / len(proc)) if proc else None,
                   "saved_minutes": delivered * int(settings.get("saved_minutes_per_file") or 0)},
        "daily": list(daily.values()),
        "employees": top(by_emp),
        "departments": top(by_dept),
        "types": [{"type": k, "count": v} for k, v in types.most_common()],
        "sizes": [{"bucket": label, "count": sizes.get(label, 0)} for _, label in SIZE_BUCKETS],
        "heatmap": heat,
        "storages": top(storages, 50),
        "sources": [{"source": k, "count": v} for k, v in sources.most_common()],
        "errors": [{**human(k), "count": v} for k, v in errors.most_common()],
        "stages": [{"stage": st, "avg_ms": int(sum(v) / len(v)) if (v := stage_sum.get(st)) else None} for st in STAGES],
        "api_keys": [{"name": names.get(kid, "—") if kid else "—", "requests": n, "avg_ms": int(avg or 0), "errors": int(err or 0)}
                     for kid, n, avg, err in api_rows],
    }


@router.get("")
async def analytics(date_from: date | None = None, date_to: date | None = None,
                    session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    return await compute(session, date_from, date_to)


@router.get("/export.xlsx")
async def export(date_from: date | None = None, date_to: date | None = None,
                 session: AsyncSession = Depends(get_session), _: Principal = Depends(viewer)):
    d = await compute(session, date_from, date_to)
    wb = Workbook()
    ws = wb.active
    ws.title = "Umumiy"
    t = d["totals"]
    for row in (("Davr", f"{d['range']['from']} — {d['range']['to']}"), ("Saqlangan fayllar", t["delivered"]),
                ("Xatolar", t["failed"]), ("Hajm (bayt)", t["size"]), ("Faol xodimlar", t["employees"]),
                ("Muvaffaqiyat", t["success_rate"]), ("O'rtacha ishlov (ms)", t["avg_ms"]), ("Tejalgan vaqt (daq)", t["saved_minutes"])):
        ws.append(list(row))

    def sheet(title: str, header: list[str], rows: list[list[Any]]) -> None:
        s = wb.create_sheet(title)
        s.append(header)
        for r in rows:
            s.append(r)

    sheet("Kunlar", ["Sana", "Saqlandi", "Xato", "Hajm (bayt)"], [[x["date"], x["delivered"], x["failed"], x["size"]] for x in d["daily"]])
    sheet("Xodimlar", ["Xodim", "Fayllar", "Hajm (bayt)"], [[x["name"], x["count"], x["size"]] for x in d["employees"]])
    sheet("Bo'limlar", ["Bo'lim", "Fayllar", "Hajm (bayt)"], [[x["name"], x["count"], x["size"]] for x in d["departments"]])
    sheet("Fayl turlari", ["Tur", "Soni"], [[x["type"], x["count"]] for x in d["types"]])
    sheet("Hajm", ["Oraliq", "Soni"], [[x["bucket"], x["count"]] for x in d["sizes"]])
    sheet("Faollik", ["Kun \\ soat", *range(24)], [[w, *d["heatmap"][i]] for i, w in enumerate(["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"])])
    sheet("Saqlash joylari", ["Nomi", "Fayllar", "Hajm (bayt)"], [[x["name"], x["count"], x["size"]] for x in d["storages"]])
    sheet("Xatolar", ["Sabab", "Soni"], [[x["title"], x["count"]] for x in d["errors"]])
    sheet("Bosqichlar", ["Bosqich", "O'rtacha (ms)"], [[x["stage"], x["avg_ms"]] for x in d["stages"]])
    sheet("API", ["Kalit", "So'rovlar", "O'rtacha (ms)", "Xatolar"], [[x["name"], x["requests"], x["avg_ms"], x["errors"]] for x in d["api_keys"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=qrdrive-analitika.xlsx"})
