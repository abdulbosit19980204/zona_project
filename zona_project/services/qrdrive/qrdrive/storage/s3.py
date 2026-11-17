"""S3-mos saqlash joylari: AWS S3, MinIO, Wasabi, Backblaze B2, Cloudflare R2 (boto3, alohida oqimda).
Havola: presigned URL (S3 cheklovi — maks. 7 kun). Muddatsiz yoki parolli havola kerak bo'lsa — tizim havolasi."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.errors import NotSupported, StorageAuthError, StorageError, StorageNotFound, StoragePermission, StorageUnavailable
from .base import HealthResult, PublicLink, Quota, RemoteEntry, RemoteFile, join

PRESIGN_MAX = 7 * 24 * 3600


def _key(path: str) -> str:
    return path.strip("/")


class S3Provider:
    kind = "s3"
    supports_links = True

    def __init__(self, bucket: str, access_key: str, secret_key: str, endpoint: str = "", region: str = "",
                 path_style: bool = False):
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3", endpoint_url=endpoint or None, region_name=region or "us-east-1",
            aws_access_key_id=access_key or None, aws_secret_access_key=secret_key or None,
            config=Config(s3={"addressing_style": "path" if path_style else "auto"}, signature_version="s3v4",
                          retries={"max_attempts": 2}, connect_timeout=15, read_timeout=300),
        )

    async def _run(self, fn, *args: Any, **kw: Any):
        from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

        try:
            return await asyncio.to_thread(fn, *args, **kw)
        except (EndpointConnectionError, ConnectionError) as e:
            raise StorageUnavailable(type(e).__name__) from e
        except NoCredentialsError as e:
            raise StorageAuthError("kalit yo'q") from e
        except ClientError as e:
            code = str(e.response.get("Error", {}).get("Code", ""))
            if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch", "AuthorizationHeaderMalformed"):
                raise StorageAuthError(code) from e
            if code in ("AccessDenied", "AllAccessDisabled"):
                raise StoragePermission(code) from e
            if code in ("NoSuchKey", "NoSuchBucket", "404", "NotFound"):
                raise StorageNotFound(code) from e
            raise StorageError(code or "S3") from e

    async def close(self) -> None:
        return None

    async def test_connection(self) -> HealthResult:
        start = time.perf_counter()
        await self._run(self.client.head_bucket, Bucket=self.bucket)
        return HealthResult(ok=True, latency_ms=int((time.perf_counter() - start) * 1000))

    async def get_quota(self) -> Quota | None:
        return None  # S3'da kvota tushunchasi yo'q

    async def ensure_folder(self, path: str) -> None:
        return None  # S3'da papka — kalit prefiksi

    async def upload(self, local_path: Path, dest_folder: str, filename: str) -> RemoteFile:
        target = join(dest_folder, filename)
        await self._run(self.client.upload_file, str(local_path), self.bucket, _key(target))
        return RemoteFile(path=target, id=_key(target), size=local_path.stat().st_size)

    async def create_public_link(self, remote: RemoteFile, expire_at: datetime | None = None,
                                 password: str | None = None, visibility: str = "public") -> PublicLink:
        if password or not expire_at or visibility == "private" or remote.is_dir:
            raise NotSupported("S3 havolasi parolsiz va muddatli bo'ladi")
        seconds = int((expire_at - datetime.now(timezone.utc)).total_seconds())
        if seconds > PRESIGN_MAX:
            raise NotSupported("S3 havolasi 7 kundan ortiq bo'lmaydi")
        url = await self._run(self.client.generate_presigned_url, "get_object",
                              Params={"Bucket": self.bucket, "Key": _key(remote.path)}, ExpiresIn=max(60, seconds))
        return PublicLink(url=url, id="", expires_at=expire_at)

    async def revoke_public_link(self, link_id: str) -> None:
        return None  # presigned URL muddati bilan o'zi tugaydi

    async def list(self, path: str) -> list[RemoteEntry]:
        prefix = _key(path) + "/" if _key(path) else ""
        data = await self._run(self.client.list_objects_v2, Bucket=self.bucket, Prefix=prefix, Delimiter="/", MaxKeys=2000)
        out = [RemoteEntry(name=p["Prefix"][len(prefix):].rstrip("/"), path="/" + p["Prefix"].rstrip("/"), is_dir=True)
               for p in data.get("CommonPrefixes", [])]
        for o in data.get("Contents", []):
            if o["Key"] == prefix:
                continue
            out.append(RemoteEntry(name=o["Key"][len(prefix):], path="/" + o["Key"], is_dir=False, size=o.get("Size"),
                                   modified=o.get("LastModified")))
        return out

    async def open_stream(self, path: str) -> AsyncIterator[bytes]:
        obj = await self._run(self.client.get_object, Bucket=self.bucket, Key=_key(path))
        body = obj["Body"]
        try:
            while chunk := await asyncio.to_thread(body.read, 256 * 1024):
                yield chunk
        finally:
            body.close()

    async def thumbnail(self, path: str) -> bytes | None:
        return None

    async def _copy_delete(self, src: str, dst: str) -> None:
        await self._run(self.client.copy_object, Bucket=self.bucket, Key=_key(dst), CopySource={"Bucket": self.bucket, "Key": _key(src)})
        await self._run(self.client.delete_object, Bucket=self.bucket, Key=_key(src))

    async def move(self, src: str, dst_folder: str) -> str:
        dst = join(dst_folder, src.rsplit("/", 1)[-1])
        await self._copy_delete(src, dst)
        return dst

    async def rename(self, path: str, new_name: str) -> str:
        dst = join(path.rsplit("/", 1)[0], new_name)
        await self._copy_delete(path, dst)
        return dst

    async def delete(self, path: str) -> None:
        await self._run(self.client.delete_object, Bucket=self.bucket, Key=_key(path))
