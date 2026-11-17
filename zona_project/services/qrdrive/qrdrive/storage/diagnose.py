"""Saqlash joyi diagnostikasi: bosqichma-bosqich tekshiradi va qaysi bosqichda, nima uchun to'xtaganini,
qanday tuzatishni oddiy tilda qaytaradi. Sinov fayli yaratiladi va darhol o'chiriladi."""
from __future__ import annotations

import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..core.errors import StorageNotFound, classify, human
from ..db.models import Storage
from . import registry
from .synology import SynologyProvider, parse_drive_folder

STEPS = ["config", "connect", "folder", "write", "link", "quota"]
TEST_DIR = "_qrdrive_tekshiruv"


def _step(key: str, ok: bool | None, detail: str = "", error: Exception | None = None, ms: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"key": key, "ok": ok, "detail": detail, "ms": ms}
    if error is not None:
        err = classify(error)
        out["error"] = human(err.kind)
        out["technical"] = (err.detail or str(error))[:300]
    return out


async def diagnose(storage: Storage, *, test_write: bool = True) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    def skip_rest(after: str) -> None:
        for k in STEPS[STEPS.index(after) + 1:]:
            steps.append(_step(k, None, "o'tkazib yuborildi"))

    # 1. Sozlama to'liqmi
    if registry.missing_credentials(storage):
        steps.append({**_step("config", False), "error": human("not_configured")})
        skip_rest("config")
        storage.status, storage.last_error = "unknown", "not_configured"
        return {"ok": False, "steps": steps}
    steps.append(_step("config", True, storage.kind))

    provider = registry.build(storage)
    test_file: str | None = None
    try:
        # 2. Ulanish / login
        t0 = time.perf_counter()
        try:
            health = await provider.test_connection()
        except Exception as e:  # noqa: BLE001
            steps.append(_step("connect", False, error=e, ms=int((time.perf_counter() - t0) * 1000)))
            skip_rest("connect")
            storage.status, storage.last_error = "down", classify(e).kind
            return {"ok": False, "steps": steps}
        detail = f"{health.latency_ms} ms"
        if isinstance(provider, SynologyProvider):
            detail += f", DSM sessiyasi: {provider.session or 'standart'}"
        steps.append(_step("connect", True, detail, ms=health.latency_ms))

        # 3. Asosiy papka (Synology Drive havolasi bo'lsa — avtomatik aniqlanadi)
        drive_id = parse_drive_folder(str(registry.get_config(storage).get("drive_folder") or "")) if storage.kind == "synology" else None
        try:
            if drive_id and isinstance(provider, SynologyProvider):
                storage.base_folder = await provider.resolve_drive_folder(drive_id)
                provider.base_folder = storage.base_folder
            note = ""
            try:
                await provider.list(storage.base_folder or "/")
            except StorageNotFound:
                await provider.ensure_folder(storage.base_folder or "/")  # yo'q bo'lsa yaratiladi (fayl yuklashda ham shunday)
                note = " (yaratildi)"
            steps.append(_step("folder", True, (storage.base_folder or "/") + note))
        except Exception as e:  # noqa: BLE001
            steps.append(_step("folder", False, storage.base_folder or "/", error=e))
            skip_rest("folder")
            storage.status, storage.last_error = "down", classify(e).kind
            return {"ok": False, "steps": steps}

        # 4. Yozish: sinov papkasi + fayl
        if test_write:
            folder = f"{(storage.base_folder or '/').rstrip('/')}/{TEST_DIR}"
            try:
                tmp = Path(tempfile.mkdtemp()) / "tekshiruv.txt"
                tmp.write_text("QR Drive tekshiruv fayli — avtomatik o'chiriladi", encoding="utf-8")
                await provider.ensure_folder(folder)
                remote = await provider.upload(tmp, folder, "tekshiruv.txt")
                test_file = folder
                steps.append(_step("write", True, remote.path))
            except Exception as e:  # noqa: BLE001
                steps.append(_step("write", False, folder, error=e))
                skip_rest("write")
                storage.status, storage.last_error = "down", classify(e).kind
                return {"ok": False, "steps": steps}

            # 5. Ommaviy havola
            if storage.link_mode == "provider" and provider.supports_links:
                try:
                    link = await provider.create_public_link(remote, datetime.now(timezone.utc) + timedelta(days=1))
                    await provider.revoke_public_link(link.id)
                    steps.append(_step("link", True, link.url.split("?")[0]))
                except Exception as e:  # noqa: BLE001
                    steps.append(_step("link", False, error=e))
            else:
                steps.append(_step("link", True, "tizim havolasi (/qrdrive/s/...)"))
        else:
            steps.append(_step("write", None, "o'tkazib yuborildi"))
            steps.append(_step("link", None, "o'tkazib yuborildi"))

        # 6. Kvota (ixtiyoriy)
        try:
            quota = await provider.get_quota()
            if quota:
                storage.quota_used, storage.quota_total = quota.used, quota.total
                steps.append(_step("quota", True, f"{quota.used / 1e9:.1f} / {quota.total / 1e9:.1f} GB"))
            else:
                steps.append(_step("quota", True, "ma'lumot yo'q"))
        except Exception:  # noqa: BLE001
            steps.append(_step("quota", True, "ma'lumot yo'q"))
    finally:
        if test_file:
            try:
                await provider.delete(test_file)
            except Exception:  # noqa: BLE001
                pass
        await provider.close()

    ok = all(s["ok"] is not False for s in steps)
    storage.status = "ok" if ok else "down"
    storage.last_error = "" if ok else next(s["error"]["kind"] for s in steps if s["ok"] is False)
    storage.latency_ms = steps[1].get("ms")
    storage.last_check_at = datetime.now(timezone.utc)
    return {"ok": ok, "steps": steps}
