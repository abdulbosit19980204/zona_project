"""Strukturaviy (JSON) loglar. Token, parol va kalitlar hech qachon logga ochiq tushmaydi."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone

trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")

_PATTERNS = [
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), "<bot-token>"),  # Telegram bot token
    (re.compile(r"/bot\d{6,12}:[A-Za-z0-9_-]{30,}"), "/bot<bot-token>"),
    (re.compile(r"qd_live_[A-Za-z0-9_-]+"), "qd_live_<hidden>"),
    (re.compile(r"(?i)(passw(or)?d|passwd|secret|token|api_key|_sid|sid)([\"']?\s*[:=]\s*[\"']?)([^\s\"'&,}]+)"), r"\1\3***"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1***"),
]


def mask(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "trace_id": trace_id.get(),
            "msg": mask(record.getMessage()),
        }
        extra = getattr(record, "data", None)
        if extra:
            data["data"] = json.loads(mask(json.dumps(extra, ensure_ascii=False, default=str)))
        if record.exc_info:
            data["exc"] = mask(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


def setup_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "aiogram.event", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
