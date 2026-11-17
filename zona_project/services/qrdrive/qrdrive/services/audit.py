"""Jurnal (kim, qachon, nima qildi) va bildirishnomalar (panel qo'ng'iroqchasi + Telegram)."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuditLog, Notification

log = logging.getLogger("qrdrive.audit")


def add_audit(session: AsyncSession, action: str, *, actor: str = "", actor_kind: str = "admin", target: str = "",
              details: dict[str, Any] | None = None) -> None:
    session.add(AuditLog(actor=actor, actor_kind=actor_kind, action=action, target=target, details=details or {}))
    log.info("audit %s", action, extra={"data": {"actor": actor, "target": target}})


# Bildirishnoma turi -> sozlamadagi kalit (notify.<kalit>)
NOTIFY_GROUP = {
    "file_failed": "failed", "storage_down": "storage", "storage_up": "storage", "quota": "quota",
    "access_request": "request", "link_expiring": "expiring", "daily_report": "daily",
}


def notify(session: AsyncSession, kind: str, title: str, body: str = "", *, level: str = "info", link: str = "") -> None:
    """Panelga yoziladi; Telegram'ga worker yuboradi (sozlamada yoqilgan bo'lsa)."""
    session.add(Notification(kind=kind, title=title, body=body, level=level, link=link))
