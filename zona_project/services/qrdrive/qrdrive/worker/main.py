"""QR Drive worker — alohida jarayon. Navbatdagi fayllarni ishlaydi va fon vazifalarini bajaradi.
Bot yoki API ishlamay qolsa ham, worker navbatni davom ettiradi (va aksincha)."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, func, select, update

from .. import settings_store
from ..core.config import config
from ..core.crypto import decrypt, sign_webhook
from ..core.errors import human
from ..core.logging import setup_logging
from ..db.models import (ApiKey, ApiRequest, AuditLog, FileEvent, FileRecord, Heartbeat, IdempotencyKey, Notification,
                         Storage, WebhookDelivery)
from ..db.session import session_scope
from ..services import pipeline, system
from ..services.audit import NOTIFY_GROUP, add_audit, notify
from ..services.telegram import TelegramClient
from ..storage import registry

log = logging.getLogger("qrdrive.worker")

CONCURRENCY = 2
WEBHOOK_DELAYS = [10, 60, 300, 1800]
STORAGE_CHECK_EVERY = 300


class Worker:
    def __init__(self) -> None:
        self.stop = asyncio.Event()
        self.started = datetime.now(timezone.utc)
        self.processed = 0
        self.sem = asyncio.Semaphore(CONCURRENCY)
        self.running: set[asyncio.Task] = set()
        self.last_storage_check = 0.0

    # ---------------- fayllar ----------------
    async def _run_file(self, fid: int) -> None:
        try:
            async with session_scope() as s:
                await pipeline.process(s, fid)
            self.processed += 1
        except Exception:  # noqa: BLE001
            log.exception("faylni ishlashda kutilmagan xato", extra={"data": {"id": fid}})
            with suppress(Exception):
                async with session_scope() as s:
                    await s.execute(update(FileRecord).where(FileRecord.id == fid, FileRecord.status == "processing")
                                    .values(status="retrying", locked_until=None,
                                            next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=60)))
                    await s.commit()
        finally:
            self.sem.release()

    async def jobs(self) -> int:
        started = 0
        while not self.stop.is_set():
            await self.sem.acquire()
            async with session_scope() as s:
                fid = await pipeline.claim_next(s)
            if fid is None:
                self.sem.release()
                break
            task = asyncio.create_task(self._run_file(fid))
            self.running.add(task)
            task.add_done_callback(self.running.discard)
            started += 1
        return started

    # ---------------- webhooklar ----------------
    async def webhooks(self) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as s:
            due = (await s.execute(select(WebhookDelivery).where(WebhookDelivery.status == "pending",
                                                                 WebhookDelivery.next_attempt_at <= now).limit(20))).scalars().all()
            if not due:
                return
            async with httpx.AsyncClient(timeout=15) as client:
                for d in due:
                    key = await s.get(ApiKey, d.api_key_id)
                    if key is None or not key.webhook_url:
                        d.status, d.error = "failed", "webhook manzili yo'q"
                        continue
                    body = json.dumps({**d.payload, "delivery_id": d.id, "sent_at": now.isoformat()}, ensure_ascii=False).encode()
                    headers = {"Content-Type": "application/json", "User-Agent": "QRDrive-Webhook/1",
                               "X-QRDrive-Event": d.event,
                               "X-QRDrive-Signature": sign_webhook(decrypt(key.webhook_secret_enc), body)}
                    d.attempts += 1
                    try:
                        r = await client.post(key.webhook_url, content=body, headers=headers)
                        d.status_code = r.status_code
                        ok = 200 <= r.status_code < 300
                        d.error = "" if ok else f"HTTP {r.status_code}"
                    except httpx.HTTPError as e:
                        ok, d.error = False, type(e).__name__
                    if ok:
                        d.status = "ok"
                    elif d.attempts > len(WEBHOOK_DELAYS):
                        d.status = "failed"
                    else:
                        d.next_attempt_at = now + timedelta(seconds=WEBHOOK_DELAYS[d.attempts - 1])
            await s.commit()

    # ---------------- bildirishnomalar (Telegram) ----------------
    async def notifications(self) -> None:
        async with session_scope() as s:
            settings = await settings_store.load(s)
            pending = (await s.execute(select(Notification).where(Notification.sent.is_(False))
                                       .order_by(Notification.id).limit(20))).scalars().all()
            if not pending:
                return
            chats = settings_store.parse_ids(settings.get("notify_chat_ids", ""))
            groups = settings.get("notify") or {}
            if not chats or not settings.get("bot_token"):
                for n in pending:
                    n.sent = True  # yuboriladigan joy yo'q — faqat panelda qoladi
                await s.commit()
                return
            icon = {"error": "🔴", "warning": "🟠", "success": "🟢"}
            async with TelegramClient.from_settings(settings) as tg:
                for n in pending:
                    if groups.get(NOTIFY_GROUP.get(n.kind, ""), True):
                        for chat in chats:
                            with suppress(Exception):
                                await tg.send_message(chat, f"{icon.get(n.level, '🔵')} {n.title}\n{n.body}".strip())
                    n.sent = True
            await s.commit()

    # ---------------- saqlash joylari ----------------
    async def storages(self) -> None:
        async with session_scope() as s:
            for st in (await s.execute(select(Storage).where(Storage.enabled.is_(True)))).scalars().all():
                before = st.status
                await registry.check(st)
                if before == "ok" and st.status == "down":
                    msg = human(st.last_error)
                    notify(s, "storage_down", f"Saqlash joyi ishlamay qoldi: {st.name}", f"{msg['title']}. {msg['hint']}",
                           level="error", link="/qr/storages")
                    add_audit(s, "storage.down", actor="worker", actor_kind="system", target=st.name)
                elif before == "down" and st.status == "ok":
                    notify(s, "storage_up", f"Saqlash joyi qayta ishlayapti: {st.name}", level="success", link="/qr/storages")
                    add_audit(s, "storage.up", actor="worker", actor_kind="system", target=st.name)
                if st.quota_total and st.quota_used and st.quota_used / st.quota_total > 0.9:
                    recent = (await s.execute(select(func.count()).select_from(Notification).where(
                        Notification.kind == "quota", Notification.title.contains(st.name),
                        Notification.at > datetime.now(timezone.utc) - timedelta(days=1)))).scalar_one()
                    if not recent:
                        pct = round(st.quota_used / st.quota_total * 100)
                        notify(s, "quota", f"{st.name}: joy {pct}% band", "Keraksiz fayllarni o'chiring yoki joy qo'shing.",
                               level="warning", link="/qr/storages")
            await s.commit()

    # ---------------- kunlik/soatlik vazifalar ----------------
    async def _once(self, s, task: str, period_key: str) -> bool:
        """Vazifa shu davrda (masalan, shu kuni) bajarilmagan bo'lsa True va belgilab qo'yadi."""
        hb = await s.get(Heartbeat, "cron") or Heartbeat(service="cron")
        info = dict(hb.info or {})
        if info.get(task) == period_key:
            return False
        info[task] = period_key
        hb.info, hb.at = info, datetime.now(timezone.utc)
        s.add(hb)
        await s.commit()
        return True

    async def maintenance(self) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as s:
            settings = await settings_store.load(s)
            tz = ZoneInfo(settings.get("timezone") or config.tz)
            local = now.astimezone(tz)
            # osilib qolgan (jarayon to'xtagan) fayllar navbatga qaytariladi
            await s.execute(update(FileRecord).where(FileRecord.status == "processing", FileRecord.locked_until < now)
                            .values(status="retrying", locked_until=None, next_attempt_at=now))
            await s.commit()

            if await self._once(s, "hourly", local.strftime("%Y%m%d%H")):
                await self._hourly(s, settings, now)
            if local.hour >= 3 and await self._once(s, "backup", local.strftime("%Y%m%d")):
                with suppress(Exception):
                    path = await system.create_backup(int(settings.get("backup_keep_days") or 14))
                    log.info("kunlik zaxira: %s", path.name)
            if (settings.get("notify") or {}).get("expiring") and local.hour >= 9 and await self._once(s, "expiring", local.strftime("%Y%m%d")):
                n = (await s.execute(select(func.count()).select_from(FileRecord).where(
                    FileRecord.status == "delivered", FileRecord.deleted_at.is_(None), FileRecord.link_expires_at > now,
                    FileRecord.link_expires_at < now + timedelta(days=3)))).scalar_one()
                if n:
                    notify(s, "link_expiring", f"{n} ta havolaning muddati 3 kun ichida tugaydi", link="/qr/files?expiring=1",
                           level="warning")
                    await s.commit()
            hh, _, mm = str(settings.get("daily_report_time") or "09:00").partition(":")
            if ((settings.get("notify") or {}).get("daily") and (local.hour, local.minute) >= (int(hh or 9), int(mm or 0))
                    and await self._once(s, "daily", local.strftime("%Y%m%d"))):
                await self._daily_report(s, now)

    async def _hourly(self, s, settings: dict[str, Any], now: datetime) -> None:
        # savat: N kundan keyin butunlay o'chirish
        cutoff = now - timedelta(days=int(settings.get("trash_days") or 30))
        for rec in (await s.execute(select(FileRecord).where(FileRecord.deleted_at < cutoff).limit(200))).scalars().all():
            try:
                from ..api.admin.files import _purge
                await _purge(s, rec)
                add_audit(s, "file.auto_purge", actor="worker", actor_kind="system", target=rec.original_name)
            except Exception:  # noqa: BLE001
                log.warning("savatdagi faylni o'chirib bo'lmadi", extra={"data": {"id": rec.id}})
        # loglarni saqlash muddati
        keep = now - timedelta(days=int(settings.get("retention_days") or 365))
        for model, col in ((AuditLog, AuditLog.at), (ApiRequest, ApiRequest.at), (FileEvent, FileEvent.at),
                           (Notification, Notification.at)):
            await s.execute(delete(model).where(col < keep))
        await s.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < now - timedelta(days=2)))
        # ishlatilmayotgan vaqtinchalik fayllar (2 kundan eski)
        used = set((await s.execute(select(FileRecord.temp_path).where(FileRecord.temp_path != ""))).scalars())
        for p in config.spool_dir.glob("*"):
            with suppress(OSError):
                if str(p) not in used and p.stat().st_mtime < time.time() - 2 * 86400:
                    p.unlink()
        await s.commit()

    async def _daily_report(self, s, now: datetime) -> None:
        since = now - timedelta(days=1)
        ok = (await s.execute(select(func.count()).select_from(FileRecord).where(
            FileRecord.status == "delivered", FileRecord.created_at >= since))).scalar_one()
        bad = (await s.execute(select(func.count()).select_from(FileRecord).where(
            FileRecord.status == "failed", FileRecord.created_at >= since))).scalar_one()
        notify(s, "daily_report", "Kunlik hisobot", f"Oxirgi 24 soatda: {ok} ta fayl saqlandi, {bad} ta xato.", link="/qr")
        await s.commit()

    # ---------------- asosiy halqa ----------------
    async def run(self) -> None:
        await system.bootstrap()
        log.info("worker ishga tushdi")
        last_beat = 0.0
        while not self.stop.is_set():
            tick = time.monotonic()
            for step in (self.jobs, self.webhooks, self.notifications, self.maintenance):
                try:
                    await step()
                except Exception:  # noqa: BLE001 — bitta vazifa xatosi qolganlarini to'xtatmaydi
                    log.exception("worker vazifasida xato: %s", step.__name__)
            if tick - self.last_storage_check > STORAGE_CHECK_EVERY:
                self.last_storage_check = tick
                with suppress(Exception):
                    await self.storages()
            if tick - last_beat > 20:
                last_beat = tick
                with suppress(Exception):
                    async with session_scope() as s:
                        queue = (await s.execute(select(func.count()).select_from(FileRecord).where(
                            FileRecord.status.in_(("queued", "retrying"))))).scalar_one()
                    await system.beat("worker", {"processed": self.processed, "queue": queue, "running": len(self.running)})
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop.wait(), timeout=1.0)
        if self.running:
            await asyncio.wait(self.running, timeout=60)


def run() -> None:
    setup_logging("worker", config.log_level)
    worker = Worker()

    async def main() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, worker.stop.set)
        await system.bootstrap()
        await system.beat("worker", started=worker.started)
        await worker.run()

    with suppress(KeyboardInterrupt):
        asyncio.run(main())


if __name__ == "__main__":
    run()
