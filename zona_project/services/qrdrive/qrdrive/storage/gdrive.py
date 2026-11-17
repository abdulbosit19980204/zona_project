"""Google Drive: Service Account (Shared Drive bilan) yoki OAuth («Google bilan ulash», refresh token).
Drive ID'larga asoslangan — yo'llar papka nomlari orqali topiladi (keshlanadi). Ommaviy havola: «anyone with link: reader»."""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from ..core.errors import NotSupported, StorageAuthError, StorageError, StorageNotFound, StoragePermission, StorageQuota, StorageUnavailable
from .base import HealthResult, PublicLink, Quota, RemoteEntry, RemoteFile, file_chunks, join

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER = "application/vnd.google-apps.folder"


def oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
                                       "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state})


async def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str,
                        transport: httpx.AsyncBaseTransport | None = None) -> str:
    async with httpx.AsyncClient(timeout=30, transport=transport) as c:
        r = await c.post(TOKEN_URL, data={"code": code, "client_id": client_id, "client_secret": client_secret,
                                          "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if r.status_code != 200 or "refresh_token" not in r.json():
        raise StorageAuthError("Google refresh token bermadi")
    return r.json()["refresh_token"]


def _esc(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveProvider:
    kind = "gdrive"
    supports_links = True

    def __init__(self, cfg: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self.mode = cfg.get("auth") or "service_account"
        self.drive_id = (cfg.get("shared_drive_id") or "").strip()
        self.root_id = (cfg.get("root_folder_id") or "").strip() or self.drive_id or "root"
        self._token: tuple[str, float] | None = None
        self._ids: dict[str, str] = {"/": self.root_id}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(900, connect=15), transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    # --- autentifikatsiya ---
    async def _access_token(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        if self.mode == "oauth":
            if not self.cfg.get("refresh_token"):
                raise StorageAuthError("Google bilan ulanmagan — «Google bilan ulash» tugmasini bosing")
            data = {"client_id": self.cfg.get("client_id"), "client_secret": self.cfg.get("client_secret"),
                    "refresh_token": self.cfg["refresh_token"], "grant_type": "refresh_token"}
        else:
            try:
                sa = json.loads(self.cfg.get("service_account_json") or "{}")
            except ValueError as e:
                raise StorageAuthError("Service Account JSON noto'g'ri") from e
            if not sa.get("private_key") or not sa.get("client_email"):
                raise StorageAuthError("Service Account JSON to'liq emas")
            now = int(time.time())
            assertion = jwt.encode({"iss": sa["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": now, "exp": now + 3600},
                                   sa["private_key"], algorithm="RS256")
            data = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        try:
            r = await self._client.post(TOKEN_URL, data=data)
        except httpx.HTTPError as e:
            raise StorageUnavailable(type(e).__name__) from e
        if r.status_code != 200:
            raise StorageAuthError(f"Google token: HTTP {r.status_code}")
        body = r.json()
        self._token = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return self._token[0]

    async def _req(self, method: str, url: str, **kw: Any) -> httpx.Response:
        headers = {**kw.pop("headers", {}), "Authorization": f"Bearer {await self._access_token()}"}
        params = {**kw.pop("params", {}), "supportsAllDrives": "true"}
        try:
            r = await self._client.request(method, url, headers=headers, params=params, **kw)
        except httpx.HTTPError as e:
            raise StorageUnavailable(type(e).__name__) from e
        if r.status_code in (401,):
            raise StorageAuthError("Google: HTTP 401")
        if r.status_code == 403:
            reason = r.text
            raise StorageQuota("Google: joy tugagan") if "storageQuotaExceeded" in reason else StoragePermission("Google: HTTP 403")
        if r.status_code == 404:
            raise StorageNotFound("Google: HTTP 404")
        if r.status_code >= 500:
            raise StorageUnavailable(f"Google: HTTP {r.status_code}")
        if r.status_code >= 400:
            raise StorageError(f"Google: HTTP {r.status_code}")
        return r

    def _list_params(self, q: str) -> dict[str, str]:
        p = {"q": q, "fields": "files(id,name,mimeType,size,modifiedTime)", "pageSize": "1000", "includeItemsFromAllDrives": "true"}
        if self.drive_id:
            p.update(corpora="drive", driveId=self.drive_id)
        return p

    # --- yo'l -> ID ---
    async def _child(self, parent: str, name: str, folder: bool | None = None) -> dict | None:
        q = f"name = '{_esc(name)}' and '{parent}' in parents and trashed = false"
        if folder is True:
            q += f" and mimeType = '{FOLDER}'"
        files = (await self._req("GET", f"{API}/files", params=self._list_params(q))).json().get("files", [])
        return files[0] if files else None

    async def _resolve(self, path: str, create: bool = False) -> str:
        path = "/" + path.strip("/")
        if path in self._ids:
            return self._ids[path]
        parent_path, _, name = path.rpartition("/")
        parent = await self._resolve(parent_path or "/", create)
        item = await self._child(parent, name, folder=create or None)
        if item is None:
            if not create:
                raise StorageNotFound(path)
            item = (await self._req("POST", f"{API}/files", json={"name": name, "mimeType": FOLDER, "parents": [parent]},
                                    params={"fields": "id"})).json()
        self._ids[path] = item["id"]
        return item["id"]

    # --- interfeys ---
    async def test_connection(self) -> HealthResult:
        start = time.perf_counter()
        if self.mode == "service_account" and not self.drive_id:
            raise StoragePermission("Service Account uchun Shared Drive ID majburiy")
        await self._req("GET", f"{API}/files/{self.root_id}", params={"fields": "id,name"})
        return HealthResult(ok=True, latency_ms=int((time.perf_counter() - start) * 1000))

    async def get_quota(self) -> Quota | None:
        if self.drive_id:
            return None  # Shared Drive'da umumiy kvota ko'rsatilmaydi
        q = (await self._req("GET", f"{API}/about", params={"fields": "storageQuota"})).json().get("storageQuota", {})
        if q.get("limit"):
            return Quota(used=int(q.get("usage", 0)), total=int(q["limit"]))
        return None

    async def ensure_folder(self, path: str) -> None:
        await self._resolve(path, create=True)

    async def upload(self, local_path: Path, dest_folder: str, filename: str) -> RemoteFile:
        parent = await self._resolve(dest_folder, create=True)
        size = local_path.stat().st_size
        meta = {"name": filename, "parents": [parent]}
        init = await self._req("POST", UPLOAD, params={"uploadType": "resumable", "fields": "id"}, json=meta,
                               headers={"X-Upload-Content-Length": str(size)})
        location = init.headers.get("location")
        if not location:
            raise StorageError("Google: yuklash manzili qaytmadi")
        r = await self._req("PUT", location, content=file_chunks(local_path), headers={"Content-Length": str(size)})
        file_id = r.json()["id"]
        target = join(dest_folder, filename)
        self._ids[target] = file_id
        return RemoteFile(path=target, id=file_id, size=size)

    async def replace(self, local_path: Path, remote: RemoteFile) -> RemoteFile:
        """Mavjud faylning tarkibini almashtirish (Drive'da shu fayl ID — havola o'zgarmaydi)."""
        fid = remote.id if remote.id and not remote.id.startswith("/") else await self._file_id(remote.path)
        size = local_path.stat().st_size
        await self._req("PATCH", f"{UPLOAD}/{fid}", params={"uploadType": "media"}, content=file_chunks(local_path),
                        headers={"Content-Length": str(size)})
        return RemoteFile(path=remote.path, id=fid, size=size)

    async def _file_id(self, remote_path: str) -> str:
        return await self._resolve(remote_path)

    async def create_public_link(self, remote: RemoteFile, expire_at: datetime | None = None,
                                 password: str | None = None, visibility: str = "public") -> PublicLink:
        if password:
            raise NotSupported("Google Drive havolasiga parol qo'yib bo'lmaydi")
        fid = remote.id if remote.id and not remote.id.startswith("/") else await self._file_id(remote.path)
        if visibility == "private":  # ruxsatsiz: faqat Drive'da kirish huquqi borlar ochadi
            info = (await self._req("GET", f"{API}/files/{fid}", params={"fields": "webViewLink"})).json()
            return PublicLink(url=info.get("webViewLink") or f"https://drive.google.com/file/d/{fid}/view", id="",
                              expires_at=None, visibility="private")
        body: dict[str, Any] = {"role": "reader", "type": "anyone"}
        perm = (await self._req("POST", f"{API}/files/{fid}/permissions", json=body, params={"fields": "id"})).json()
        info = (await self._req("GET", f"{API}/files/{fid}", params={"fields": "webViewLink"})).json()
        return PublicLink(url=info.get("webViewLink") or f"https://drive.google.com/file/d/{fid}/view", id=f"{fid}:{perm['id']}",
                          expires_at=expire_at)

    async def revoke_public_link(self, link_id: str) -> None:
        if ":" in link_id:
            fid, pid = link_id.split(":", 1)
            try:
                await self._req("DELETE", f"{API}/files/{fid}/permissions/{pid}")
            except StorageNotFound:
                pass

    async def list(self, path: str) -> list[RemoteEntry]:
        parent = await self._resolve(path)
        files = (await self._req("GET", f"{API}/files", params=self._list_params(f"'{parent}' in parents and trashed = false"))).json()["files"]
        out = []
        for f in files:
            is_dir = f["mimeType"] == FOLDER
            p = join(path, f["name"])
            self._ids[p] = f["id"]
            out.append(RemoteEntry(name=f["name"], path=p, is_dir=is_dir, size=int(f["size"]) if f.get("size") else None,
                                   modified=datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")) if f.get("modifiedTime") else None))
        return sorted(out, key=lambda e: (not e.is_dir, e.name.lower()))

    async def open_stream(self, path: str) -> AsyncIterator[bytes]:
        fid = await self._file_id(path)
        headers = {"Authorization": f"Bearer {await self._access_token()}"}
        async with self._client.stream("GET", f"{API}/files/{fid}", params={"alt": "media", "supportsAllDrives": "true"},
                                       headers=headers) as r:
            if r.status_code == 404:
                raise StorageNotFound(path)
            if r.status_code >= 400:
                raise StorageError(f"Google: HTTP {r.status_code}")
            async for chunk in r.aiter_bytes(256 * 1024):
                yield chunk

    async def thumbnail(self, path: str) -> bytes | None:
        return None

    async def move(self, src: str, dst_folder: str) -> str:
        fid = await self._file_id(src)
        old_parent = await self._resolve(src.rsplit("/", 1)[0] or "/")
        new_parent = await self._resolve(dst_folder, create=True)
        await self._req("PATCH", f"{API}/files/{fid}", params={"addParents": new_parent, "removeParents": old_parent}, json={})
        dst = join(dst_folder, src.rsplit("/", 1)[-1])
        self._ids.pop("/" + src.strip("/"), None)
        self._ids[dst] = fid
        return dst

    async def rename(self, path: str, new_name: str) -> str:
        fid = await self._file_id(path)
        await self._req("PATCH", f"{API}/files/{fid}", json={"name": new_name})
        dst = join(path.rsplit("/", 1)[0], new_name)
        self._ids.pop("/" + path.strip("/"), None)
        self._ids[dst] = fid
        return dst

    async def delete(self, path: str) -> None:
        try:
            fid = await self._file_id(path)
        except StorageNotFound:
            return
        await self._req("DELETE", f"{API}/files/{fid}")
        self._ids.pop("/" + path.strip("/"), None)
