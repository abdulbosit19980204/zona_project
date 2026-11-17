"""Lokal disk yoki serverga ulangan tarmoq papkasi (SMB/NFS). Ommaviy havola — tizimning o'z havolasi orqali."""
from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from ..core.errors import NotSupported, StorageNotFound, StoragePermission, StorageUnavailable
from .base import HealthResult, PublicLink, Quota, RemoteEntry, RemoteFile, join


class LocalProvider:
    kind = "local"
    supports_links = False

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _abs(self, path: str) -> Path:
        target = (self.root / path.lstrip("/")).resolve()
        if target != self.root and self.root not in target.parents:
            raise StoragePermission("papkadan tashqariga chiqish taqiqlangan")
        return target

    async def close(self) -> None:
        return None

    async def test_connection(self) -> HealthResult:
        start = time.perf_counter()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".qrdrive-probe"
            probe.write_bytes(b"ok")
            probe.unlink()
        except PermissionError as e:
            raise StoragePermission(str(e)) from e
        except OSError as e:
            raise StorageUnavailable(str(e)) from e
        return HealthResult(ok=True, latency_ms=int((time.perf_counter() - start) * 1000))

    async def get_quota(self) -> Quota | None:
        usage = shutil.disk_usage(self.root if self.root.exists() else self.root.parent)
        return Quota(used=usage.used, total=usage.total)

    async def ensure_folder(self, path: str) -> None:
        self._abs(path).mkdir(parents=True, exist_ok=True)

    async def upload(self, local_path: Path, dest_folder: str, filename: str) -> RemoteFile:
        folder = self._abs(dest_folder)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / filename
        await asyncio.to_thread(shutil.copyfile, local_path, target)
        rel = join(dest_folder, filename)
        return RemoteFile(path=rel, id=rel, size=target.stat().st_size)

    async def create_public_link(self, remote: RemoteFile, expire_at=None, password=None, visibility: str = "public") -> PublicLink:
        raise NotSupported("lokal disk o'z havolasini bera olmaydi")

    async def revoke_public_link(self, link_id: str) -> None:
        return None

    async def list(self, path: str) -> list[RemoteEntry]:
        folder = self._abs(path)
        if not folder.is_dir():
            raise StorageNotFound(path)
        out = []
        for p in sorted(folder.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if p.name.startswith(".qrdrive"):
                continue
            st = p.stat()
            out.append(RemoteEntry(name=p.name, path=join(path, p.name), is_dir=p.is_dir(),
                                   size=None if p.is_dir() else st.st_size,
                                   modified=datetime.fromtimestamp(st.st_mtime, timezone.utc)))
        return out

    async def open_stream(self, path: str) -> AsyncIterator[bytes]:
        target = self._abs(path)
        if not target.is_file():
            raise StorageNotFound(path)
        with open(target, "rb") as fh:
            while chunk := await asyncio.to_thread(fh.read, 256 * 1024):
                yield chunk

    async def thumbnail(self, path: str) -> bytes | None:
        return None

    async def move(self, src: str, dst_folder: str) -> str:
        folder = self._abs(dst_folder)
        folder.mkdir(parents=True, exist_ok=True)
        source = self._abs(src)
        if not source.exists():
            raise StorageNotFound(src)
        shutil.move(source, folder / source.name)
        return join(dst_folder, source.name)

    async def rename(self, path: str, new_name: str) -> str:
        source = self._abs(path)
        if not source.exists():
            raise StorageNotFound(path)
        target = source.with_name(new_name)
        source.rename(target)
        return join(path.rsplit("/", 1)[0], new_name)

    async def delete(self, path: str) -> None:
        target = self._abs(path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
