"""Bazadagi Storage yozuvidan provayder obyektini yasash va holatini tekshirish."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..core.config import config
from ..core.crypto import decrypt_json, encrypt_json
from ..core.errors import QRDriveError, classify, human
from ..db.models import Storage
from .base import FIELDS, StorageProvider
from .gdrive import GoogleDriveProvider
from .local import LocalProvider
from .s3 import S3Provider
from .webdav import WebDAVProvider
from .synology import SynologyProvider, parse_drive_folder


def secret_keys(kind: str) -> set[str]:
    return {f["key"] for f in FIELDS.get(kind, []) if f.get("secret")}


def get_config(storage: Storage) -> dict[str, Any]:
    return decrypt_json(storage.config_enc)


def set_config(storage: Storage, values: dict[str, Any]) -> None:
    """Maxfiy maydon bo'sh kelsa — eskisi saqlanadi («O'zgartirish» bosilmagan)."""
    current = get_config(storage) if storage.config_enc else {}
    merged = dict(current)
    for f in FIELDS.get(storage.kind, []):
        key = f["key"]
        if key not in values:
            continue
        if f.get("secret") and not values[key]:
            continue
        merged[key] = values[key]
    storage.config_enc = encrypt_json(merged)


def public_config(storage: Storage) -> dict[str, Any]:
    cfg = get_config(storage)
    out = {}
    for f in FIELDS.get(storage.kind, []):
        if f.get("secret"):
            out[f"{f['key']}_set"] = bool(cfg.get(f["key"]))
        else:
            out[f["key"]] = cfg.get(f["key"], f.get("default", ""))
    if storage.kind == "gdrive":
        out["google_connected"] = bool(cfg.get("refresh_token"))
    return out


def build(storage: Storage) -> StorageProvider:
    cfg = get_config(storage)
    if storage.kind == "synology":
        return SynologyProvider(cfg.get("url", ""), cfg.get("username", ""), cfg.get("password", ""),
                                verify_ssl=bool(cfg.get("verify_ssl", True)), base_folder=storage.base_folder)
    if storage.kind == "local":
        return LocalProvider(cfg.get("root") or str(config.local_storage_default))
    if storage.kind == "webdav":
        return WebDAVProvider(cfg.get("url", ""), cfg.get("username", ""), cfg.get("password", ""),
                              nextcloud=bool(cfg.get("nextcloud", True)), verify_ssl=bool(cfg.get("verify_ssl", True)))
    if storage.kind == "s3":
        return S3Provider(cfg.get("bucket", ""), cfg.get("access_key", ""), cfg.get("secret_key", ""),
                          endpoint=cfg.get("endpoint", ""), region=cfg.get("region", ""), path_style=bool(cfg.get("path_style")))
    if storage.kind == "gdrive":
        return GoogleDriveProvider(cfg)
    raise QRDriveError(f"Noma'lum saqlash joyi turi: {storage.kind}")


REQUIRED = {"synology": ("username", "password"), "webdav": ("url", "username", "password"),
            "s3": ("bucket", "access_key", "secret_key")}


def missing_credentials(storage: Storage) -> bool:
    cfg = get_config(storage)
    if storage.kind == "gdrive":
        mode = cfg.get("auth") or "service_account"
        keys = ("service_account_json", "shared_drive_id") if mode == "service_account" else ("client_id", "client_secret")
    else:
        keys = REQUIRED.get(storage.kind, ())
    return any(not str(cfg.get(k) or "").strip() for k in keys)


async def check(storage: Storage) -> dict[str, Any]:
    """Ulanishni tekshiradi va natijani yozuvga yozadi (commit chaqiruvchida)."""
    if missing_credentials(storage):  # login/parol kiritilmagan — serverga bekorga ulanilmaydi
        storage.status, storage.last_error, storage.latency_ms = "unknown", "not_configured", None
        storage.last_check_at = datetime.now(timezone.utc)
        return {"ok": False, **human("not_configured")}
    provider = build(storage)
    try:
        health = await provider.test_connection()
        drive_id = parse_drive_folder(str(get_config(storage).get("drive_folder") or "")) if storage.kind == "synology" else None
        if drive_id and isinstance(provider, SynologyProvider):
            storage.base_folder = await provider.resolve_drive_folder(drive_id)
            provider.base_folder = storage.base_folder
        quota = None
        try:
            quota = await provider.get_quota()
        except Exception:  # kvota ixtiyoriy
            quota = None
        storage.status, storage.last_error, storage.latency_ms = "ok", "", health.latency_ms
        if quota:
            storage.quota_used, storage.quota_total = quota.used, quota.total
        result = {"ok": True, "latency_ms": health.latency_ms}
    except Exception as exc:  # noqa: BLE001
        err = classify(exc)
        storage.status, storage.last_error, storage.latency_ms = "down", err.kind, None
        result = {"ok": False, **human(err.kind)}
    finally:
        await provider.close()
    storage.last_check_at = datetime.now(timezone.utc)
    return result
