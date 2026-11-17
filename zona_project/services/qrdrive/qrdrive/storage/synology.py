"""Synology DSM File Station API (login, papka, yuklash, ommaviy havola, ro'yxat, yuklab olish, ...).
Eski kadrlar-bot/synology.py mantig'i asosida, httpx bilan."""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..core.errors import (NotSupported, QRDriveError, Storage2FA, StorageAccountDisabled, StorageAppDenied, StorageAuthError, StorageError,
                           StorageIPBlocked, StorageNotFound, StoragePasswordExpired, StoragePermission, StorageQuota,
                           StorageUnavailable)
from .base import HealthResult, PublicLink, Quota, RemoteEntry, RemoteFile, join

DRIVE_ID = re.compile(r"(?:file_id=|^)(\d{6,})")


def parse_drive_folder(value: str) -> str | None:
    """«https://file.stargroup.uz/#file_id=984701843502314054» yoki faqat ID -> "984701843502314054"."""
    m = DRIVE_ID.search((value or "").strip())
    return m.group(1) if m else None


def filestation_to_drive(path: str) -> str:
    """File Station yo'li -> Synology Drive yo'li (teskarisi)."""
    if path == "/home" or path.startswith("/home/"):
        return "/mydrive" + path[len("/home"):]
    return "/team-folders" + path


def drive_to_filestation(display_path: str) -> str:
    """Synology Drive yo'li -> File Station yo'li: jamoa papkasi = umumiy papka, My Drive = /home."""
    if display_path.startswith("/team-folders/"):
        return "/" + display_path[len("/team-folders/"):].strip("/")
    if display_path.startswith("/mydrive"):
        return "/home" + display_path[len("/mydrive"):].rstrip("/")
    return display_path.rstrip("/") or "/"


# Sessiya eskirgan / yaroqsiz bo'lganda qaytadigan kodlar
RELOGIN_CODES = {105, 106, 107, 119}
AUTH_CODES = {400, 401, 402, 403, 404, 406, 407}


def _auth_error(code: int | None) -> QRDriveError:
    if code == 400:
        return StorageAuthError(f"DSM: login yoki parol noto'g'ri (kod {code})")
    if code == 401:
        return StorageAccountDisabled(f"DSM: akkaunt o'chirilgan (kod {code})")
    if code in (402, 405):
        return StorageAppDenied(f"DSM: ilovaga ruxsat yo'q (kod {code})")
    if code in (403, 404, 406):
        return Storage2FA(f"DSM: 2 bosqichli tekshiruv talab qilinadi (kod {code})")
    if code == 407:
        return StorageIPBlocked(f"DSM: IP manzil bloklangan (kod {code})")
    if code in (408, 409, 410):
        return StoragePasswordExpired(f"DSM: parol muddati tugagan (kod {code})")
    return StorageAuthError(f"DSM login xato kodi {code}")


def _raise(api: str, code: int | None) -> None:
    if api == "SYNO.API.Auth":
        raise _auth_error(code)
    if code in (105, 407):
        raise StoragePermission(f"{api}: ruxsat yo'q (kod {code})")
    if code == 408:
        raise StorageNotFound(f"{api}: topilmadi (kod {code})")
    if code in (415, 416):
        raise StorageQuota(f"{api}: joy yetarli emas (kod {code})")
    raise StorageError(f"{api}: xato kodi {code}")


class SynologyProvider:
    kind = "synology"
    supports_links = True

    def __init__(self, url: str, username: str, password: str, verify_ssl: bool = True, base_folder: str = "/",
                 transport: httpx.AsyncBaseTransport | None = None, drive_links: bool = False):
        self.base = url.rstrip("/")
        self.entry = f"{self.base}/webapi/entry.cgi"
        self.username, self.password = username, password
        self.base_folder = base_folder or "/"
        self.sid: str | None = None
        # Synology Drive havolalari (file.stargroup.uz/d/s/..., /d/f/...) — Drive papkasi berilgan bo'lsa
        self.drive_links = drive_links
        self.drive_wait = 90  # Drive yangi faylni File Station'dan ~5-10 soniyada ko'radi
        self.session: str | None = None  # birinchi muvaffaqiyatli sessiya nomi eslab qolinadi
        self._client = httpx.AsyncClient(verify=verify_ssl, timeout=httpx.Timeout(900, connect=15), transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    # Sessiya nomlari navbat bilan: foydalanuvchiga File Station ilovasi yopiq, lekin Synology Drive ochiq bo'lishi mumkin
    # (bunda "FileStation" sessiyasi 405 bilan rad etiladi, Drive sessiyasi esa File Station API'larini ham ochadi).
    SESSIONS = ("SynologyDrive", "FileStation", "")

    async def login(self) -> None:
        last: QRDriveError | None = None
        for session in ([self.session] if self.session is not None else self.SESSIONS):
            params = {"api": "SYNO.API.Auth", "version": "6", "method": "login", "account": self.username,
                      "passwd": self.password, "format": "sid"}
            if session:
                params["session"] = session
            try:
                data = await self._call(params, auth=False, method="POST")  # parol URL'da ko'rinmasin
            except StorageAppDenied as e:
                last = e
                continue
            self.sid, self.session = data["sid"], session
            return
        raise last or StorageAuthError("DSM login muvaffaqiyatsiz")

    async def _call(self, params: dict[str, Any], auth: bool = True, retry: bool = True, method: str = "GET") -> dict:
        if auth and not self.sid:
            await self.login()
        query = {**params, "_sid": self.sid} if auth else params
        if method == "POST":
            r = await self._client.post(self.entry, data=query)
        else:
            r = await self._client.get(self.entry, params=query)
        if r.status_code >= 500:
            raise StorageUnavailable(f"HTTP {r.status_code}")
        r.raise_for_status()
        body = r.json()
        if body.get("success"):
            return body.get("data") or {}
        code = (body.get("error") or {}).get("code")
        if auth and retry and code in RELOGIN_CODES:
            self.sid = None
            return await self._call(params, auth=True, retry=False, method=method)
        _raise(str(params.get("api")), code)
        return {}

    async def resolve_drive_folder(self, file_id: str) -> str:
        """Synology Drive papkasi ID'sidan (brauzer manzilidagi #file_id=...) File Station yo'lini aniqlaydi."""
        last: Exception | None = None
        for path in (f"id:{file_id}", json.dumps(f"id:{file_id}")):
            try:
                data = await self._call({"api": "SYNO.SynologyDrive.Files", "version": "2", "method": "get", "path": path})
            except (StorageError, StorageNotFound, StoragePermission) as e:
                last = e
                continue
            item = data if ("display_path" in data or "path" in data) else (data.get("items") or [{}])[0]
            display = item.get("display_path") or item.get("path") or ""
            if display:
                return drive_to_filestation(display)
        raise StorageNotFound(f"Synology Drive papkasi topilmadi: {file_id} ({last})")

    # --- interfeys ---
    async def test_connection(self) -> HealthResult:
        start = time.perf_counter()
        self.sid = None
        await self.login()
        await self._call({"api": "SYNO.FileStation.List", "version": "2", "method": "list_share", "limit": "1"})
        return HealthResult(ok=True, latency_ms=int((time.perf_counter() - start) * 1000))

    async def get_quota(self) -> Quota | None:
        share = "/" + self.base_folder.strip("/").split("/")[0] if self.base_folder.strip("/") else ""
        data = await self._call({"api": "SYNO.FileStation.List", "version": "2", "method": "list_share",
                                 "additional": json.dumps(["volume_status"])})
        for item in data.get("shares", []):
            if not share or item.get("path") == share:
                vs = (item.get("additional") or {}).get("volume_status") or {}
                total, free = int(vs.get("totalspace") or 0), int(vs.get("freespace") or 0)
                if total:
                    return Quota(used=total - free, total=total)
        return None

    async def ensure_folder(self, path: str) -> None:
        parent, _, name = path.rstrip("/").rpartition("/")
        if not name:
            return
        await self._call({"api": "SYNO.FileStation.CreateFolder", "version": "2", "method": "create",
                          "folder_path": json.dumps([parent or "/"], ensure_ascii=False),
                          "name": json.dumps([name], ensure_ascii=False), "force_parent": "true"})

    async def upload(self, local_path: Path, dest_folder: str, filename: str) -> RemoteFile:
        for attempt in (1, 2):
            if not self.sid:
                await self.login()
            size = local_path.stat().st_size
            with open(local_path, "rb") as fh:
                # Synology talabi: fayl maydoni eng oxirida
                r = await self._client.post(
                    self.entry,
                    params={"api": "SYNO.FileStation.Upload", "version": "2", "method": "upload", "_sid": self.sid},
                    data={"path": dest_folder, "create_parents": "true", "overwrite": "true"},
                    files={"file": (filename, fh, "application/octet-stream")},
                )
            if r.status_code >= 500:
                raise StorageUnavailable(f"HTTP {r.status_code}")
            body = r.json()
            if body.get("success"):
                path = f"{dest_folder.rstrip('/')}/{filename}"
                return RemoteFile(path=path, id=path, size=size)
            code = (body.get("error") or {}).get("code")
            if attempt == 1 and code in RELOGIN_CODES:
                self.sid = None
                continue
            _raise("SYNO.FileStation.Upload", code)
        raise StorageError("Upload muvaffaqiyatsiz")

    async def _drive_file(self, path: str) -> dict:
        """Synology Drive fayl ma'lumoti (file_id, permanent_link). Yangi faylni indekslashini kutadi."""
        drive_path = json.dumps(filestation_to_drive(path), ensure_ascii=False)
        deadline = time.monotonic() + self.drive_wait
        while True:
            try:
                return await self._call({"api": "SYNO.SynologyDrive.Files", "version": "2", "method": "get", "path": drive_path})
            except (StorageError, StorageNotFound):
                if time.monotonic() > deadline:
                    raise StorageNotFound(f"Synology Drive faylni ko'rmadi: {path}") from None
                await asyncio.sleep(0.5)

    async def create_public_link(self, remote: RemoteFile, expire_at: datetime | None = None,
                                 password: str | None = None, visibility: str = "public") -> PublicLink:
        if self.drive_links:
            info = await self._drive_file(remote.path)
            if visibility == "private":
                # Private: faqat NAS'da shu faylga ruxsati borlar ochadi
                return PublicLink(url=f"{self.base}/d/f/{info['permanent_link']}", id=f"drive:{info['file_id']}",
                                  expires_at=None, visibility="private")
            if expire_at or password:
                raise NotSupported("Synology Drive ommaviy havolasiga API orqali muddat/parol qo'yib bo'lmaydi")
            data = await self._call({"api": "SYNO.SynologyDrive.AdvanceSharing", "version": "1", "method": "create",
                                     "path": json.dumps(f"id:{info['file_id']}")}, method="POST")
            if not data.get("url"):
                raise StorageError("Synology Drive havola qaytarmadi")
            return PublicLink(url=data["url"], id=f"drive:{info['file_id']}", expires_at=None, visibility="public")
        if visibility == "private":
            raise NotSupported("Private havola faqat Synology Drive papkasi bilan ishlaydi")
        params = {"api": "SYNO.FileStation.Sharing", "version": "3", "method": "create",
                  "path": json.dumps([remote.path], ensure_ascii=False)}
        if expire_at:
            params["date_expired"] = expire_at.date().isoformat()
        if password:
            params["password"] = password
        data = await self._call(params, method="POST")
        links = data.get("links") or []
        if not links or not links[0].get("url"):
            raise StorageError("Havola qaytmadi")
        return PublicLink(url=links[0]["url"], id=str(links[0].get("id", "")), expires_at=expire_at)

    async def revoke_public_link(self, link_id: str) -> None:
        if link_id.startswith("drive:"):
            # Synology Drive havolasini API orqali o'chirib bo'lmaydi — Synology Drive'da «Share» oynasidan o'chiriladi
            raise NotSupported("Synology Drive havolasini NAS'dagi «Share» oynasidan o'chiring")
        if link_id:
            await self._call({"api": "SYNO.FileStation.Sharing", "version": "3", "method": "delete",
                              "id": json.dumps([link_id])})

    async def list(self, path: str) -> list[RemoteEntry]:
        data = await self._call({"api": "SYNO.FileStation.List", "version": "2", "method": "list",
                                 "folder_path": path, "additional": json.dumps(["size", "time"]), "limit": "2000"})
        out = []
        for f in data.get("files", []):
            add = f.get("additional") or {}
            mtime = (add.get("time") or {}).get("mtime")
            out.append(RemoteEntry(name=f["name"], path=f["path"], is_dir=bool(f.get("isdir")),
                                   size=add.get("size") if not f.get("isdir") else None,
                                   modified=datetime.fromtimestamp(mtime, timezone.utc) if mtime else None))
        return out

    async def open_stream(self, path: str) -> AsyncIterator[bytes]:
        if not self.sid:
            await self.login()
        params = {"api": "SYNO.FileStation.Download", "version": "2", "method": "download",
                  "path": json.dumps([path], ensure_ascii=False), "mode": "download", "_sid": self.sid}
        async with self._client.stream("GET", self.entry, params=params) as r:
            if r.status_code == 404:
                raise StorageNotFound(path)
            ctype = r.headers.get("content-type", "")
            if "application/json" in ctype:  # xato JSON ko'rinishida qaytadi
                body = json.loads(await r.aread())
                _raise("SYNO.FileStation.Download", (body.get("error") or {}).get("code"))
            async for chunk in r.aiter_bytes(256 * 1024):
                yield chunk

    async def thumbnail(self, path: str) -> bytes | None:
        if not self.sid:
            await self.login()
        r = await self._client.get(self.entry, params={"api": "SYNO.FileStation.Thumb", "version": "2", "method": "get",
                                                       "path": path, "size": "medium", "_sid": self.sid})
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return r.content
        return None

    async def _wait_task(self, api: str, taskid: str) -> None:
        for _ in range(120):
            data = await self._call({"api": api, "version": "2" if "Delete" in api else "3", "method": "status",
                                     "taskid": taskid})
            if data.get("finished"):
                if data.get("error"):
                    _raise(api, (data.get("error") or {}).get("code"))
                return
            await asyncio.sleep(0.5)
        raise StorageError(f"{api}: vaqt tugadi")

    async def move(self, src: str, dst_folder: str) -> str:
        await self.ensure_folder(dst_folder)
        api = "SYNO.FileStation.CopyMove"
        data = await self._call({"api": api, "version": "3", "method": "start", "path": json.dumps([src], ensure_ascii=False),
                                 "dest_folder_path": dst_folder, "overwrite": "false", "remove_src": "true"})
        await self._wait_task(api, data["taskid"])
        return join(dst_folder, src.rsplit("/", 1)[-1])

    async def rename(self, path: str, new_name: str) -> str:
        await self._call({"api": "SYNO.FileStation.Rename", "version": "2", "method": "rename",
                          "path": json.dumps([path], ensure_ascii=False), "name": json.dumps([new_name], ensure_ascii=False)})
        return f"{path.rsplit('/', 1)[0]}/{new_name}"

    async def delete(self, path: str) -> None:
        api = "SYNO.FileStation.Delete"
        data = await self._call({"api": api, "version": "2", "method": "start",
                                 "path": json.dumps([path], ensure_ascii=False), "recursive": "true"})
        await self._wait_task(api, data["taskid"])
