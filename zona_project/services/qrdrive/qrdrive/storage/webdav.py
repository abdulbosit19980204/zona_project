"""WebDAV / Nextcloud. Ommaviy havola — Nextcloud OCS Share API (boshqa WebDAV serverlarda tizim havolasi)."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import httpx

from ..core.errors import (NotSupported, StorageAuthError, StorageError, StorageNotFound, StoragePermission, StorageQuota,
                           StorageUnavailable)
from .base import HealthResult, PublicLink, Quota, RemoteEntry, RemoteFile, file_chunks, join

NS = {"d": "DAV:"}
PROPFIND = b"""<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>
<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><d:quota-used-bytes/><d:quota-available-bytes/>
</d:prop></d:propfind>"""


def _check(r: httpx.Response, what: str) -> None:
    if r.status_code in (401,):
        raise StorageAuthError(f"{what}: HTTP 401")
    if r.status_code == 403:
        raise StoragePermission(f"{what}: HTTP 403")
    if r.status_code == 404:
        raise StorageNotFound(f"{what}: HTTP 404")
    if r.status_code == 507:
        raise StorageQuota(f"{what}: HTTP 507")
    if r.status_code >= 500:
        raise StorageUnavailable(f"{what}: HTTP {r.status_code}")
    if r.status_code >= 400:
        raise StorageError(f"{what}: HTTP {r.status_code}")


class WebDAVProvider:
    kind = "webdav"

    def __init__(self, url: str, username: str, password: str, nextcloud: bool = True, verify_ssl: bool = True,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.root = url.rstrip("/")
        self.root_path = urlsplit(self.root).path.rstrip("/")
        self.nextcloud = nextcloud
        self.supports_links = nextcloud
        self.ocs = self.root.split("/remote.php", 1)[0] + "/ocs/v2.php/apps/files_sharing/api/v1/shares" if "/remote.php" in self.root else ""
        self._client = httpx.AsyncClient(auth=(username, password), verify=verify_ssl, timeout=httpx.Timeout(900, connect=15),
                                         transport=transport, headers={"OCS-APIRequest": "true"})

    def _url(self, path: str) -> str:
        return self.root + quote("/" + path.strip("/")) if path.strip("/") else self.root + "/"

    async def close(self) -> None:
        await self._client.aclose()

    async def _propfind(self, path: str, depth: str) -> ET.Element:
        r = await self._client.request("PROPFIND", self._url(path), content=PROPFIND,
                                       headers={"Depth": depth, "Content-Type": "application/xml"})
        _check(r, "PROPFIND")
        return ET.fromstring(r.content)

    async def test_connection(self) -> HealthResult:
        start = time.perf_counter()
        await self._propfind("/", "0")
        return HealthResult(ok=True, latency_ms=int((time.perf_counter() - start) * 1000))

    async def get_quota(self) -> Quota | None:
        tree = await self._propfind("/", "0")
        used = tree.find(".//d:quota-used-bytes", NS)
        free = tree.find(".//d:quota-available-bytes", NS)
        if used is not None and free is not None and used.text and free.text and int(free.text) >= 0:
            return Quota(used=int(used.text), total=int(used.text) + int(free.text))
        return None

    async def ensure_folder(self, path: str) -> None:
        current = ""
        for part in [p for p in path.split("/") if p]:
            current += "/" + part
            r = await self._client.request("MKCOL", self._url(current))
            if r.status_code not in (201, 405, 301):  # 405 — allaqachon bor
                _check(r, "MKCOL")

    async def upload(self, local_path: Path, dest_folder: str, filename: str) -> RemoteFile:
        target = join(dest_folder, filename)
        size = local_path.stat().st_size
        r = await self._client.put(self._url(target), content=file_chunks(local_path), headers={"Content-Length": str(size)})
        _check(r, "PUT")
        return RemoteFile(path=target, id=target, size=size)

    async def create_public_link(self, remote: RemoteFile, expire_at: datetime | None = None,
                                 password: str | None = None) -> PublicLink:
        if not self.nextcloud or not self.ocs:
            raise NotSupported("WebDAV ommaviy havola bera olmaydi")
        data = {"path": remote.path, "shareType": "3", "permissions": "1"}
        if expire_at:
            data["expireDate"] = expire_at.date().isoformat()
        if password:
            data["password"] = password
        r = await self._client.post(self.ocs, data=data, params={"format": "json"})
        _check(r, "OCS share")
        share = (r.json().get("ocs") or {}).get("data") or {}
        if not share.get("url"):
            raise StorageError("Nextcloud havola qaytarmadi")
        return PublicLink(url=share["url"], id=str(share.get("id", "")), expires_at=expire_at)

    async def revoke_public_link(self, link_id: str) -> None:
        if link_id and self.ocs:
            r = await self._client.delete(f"{self.ocs}/{link_id}", params={"format": "json"})
            if r.status_code not in (200, 404):
                _check(r, "OCS delete")

    async def list(self, path: str) -> list[RemoteEntry]:
        tree = await self._propfind(path, "1")
        out = []
        base = (self.root_path + "/" + path.strip("/")).rstrip("/")
        for resp in tree.findall("d:response", NS):
            href = unquote(resp.findtext("d:href", "", NS)).rstrip("/")
            if href == base or href == base + "/":
                continue
            rel = href[len(self.root_path):] if href.startswith(self.root_path) else href
            is_dir = resp.find(".//d:resourcetype/d:collection", NS) is not None
            size = resp.findtext(".//d:getcontentlength", None, NS)
            mod = resp.findtext(".//d:getlastmodified", None, NS)
            out.append(RemoteEntry(name=rel.rstrip("/").rsplit("/", 1)[-1], path=rel or "/", is_dir=is_dir,
                                   size=int(size) if size and not is_dir else None,
                                   modified=parsedate_to_datetime(mod) if mod else None))
        return sorted(out, key=lambda e: (not e.is_dir, e.name.lower()))

    async def open_stream(self, path: str) -> AsyncIterator[bytes]:
        async with self._client.stream("GET", self._url(path)) as r:
            _check(r, "GET")
            async for chunk in r.aiter_bytes(256 * 1024):
                yield chunk

    async def thumbnail(self, path: str) -> bytes | None:
        return None

    async def _move(self, src: str, dst: str) -> None:
        r = await self._client.request("MOVE", self._url(src), headers={"Destination": self._url(dst), "Overwrite": "F"})
        _check(r, "MOVE")

    async def move(self, src: str, dst_folder: str) -> str:
        await self.ensure_folder(dst_folder)
        dst = join(dst_folder, src.rsplit("/", 1)[-1])
        await self._move(src, dst)
        return dst

    async def rename(self, path: str, new_name: str) -> str:
        dst = join(path.rsplit("/", 1)[0], new_name)
        await self._move(path, dst)
        return dst

    async def delete(self, path: str) -> None:
        r = await self._client.delete(self._url(path))
        if r.status_code != 404:
            _check(r, "DELETE")

