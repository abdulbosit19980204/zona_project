"""QR Drive Python SDK: fayl yuklash va QR olish (REST API v1 ustida yengil async klient).

    from qrdrive_sdk import QRDriveClient
    res = await QRDriveClient("https://qr.firma.uz", "qd_live_...").upload("hujjat.pdf", telegram_id=123)
    print(res.url, res.qr_png[:8])
"""
from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import httpx

__all__ = ["QRDriveClient", "QRDriveError", "UploadResult"]
__version__ = "0.1.0"


class QRDriveError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


@dataclass
class UploadResult:
    id: int
    status: str
    url: str = ""
    qr_base64: str = ""
    remote_path: str = ""
    expires_at: str | None = None
    error: dict[str, str] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status == "delivered"

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    @property
    def qr_png(self) -> bytes:
        return base64.b64decode(self.qr_base64) if self.qr_base64 else b""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> UploadResult:
        return cls(id=data["id"], status=data["status"], url=data.get("url", ""), qr_base64=data.get("qr_base64", ""),
                   remote_path=data.get("remote_path", ""), expires_at=data.get("expires_at"), error=data.get("error"), raw=data)


class QRDriveClient:
    """`url` — QR Drive manzili (masalan https://qr.firma.uz), `api_key` — admin panelda yaratilgan kalit."""

    def __init__(self, url: str, api_key: str, *, timeout: float = 120, transport: httpx.AsyncBaseTransport | None = None):
        self.base = url.rstrip("/") + "/qrdrive/api/v1"
        self._client = httpx.AsyncClient(headers={"Authorization": f"Bearer {api_key}", "User-Agent": f"qrdrive-sdk/{__version__}"},
                                         timeout=timeout, transport=transport)

    async def __aenter__(self) -> QRDriveClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        r = await self._client.request(method, self.base + path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise QRDriveError(r.status_code, str(detail))
        return r

    async def upload(self, file: str | Path | bytes | IO[bytes] | None = None, *, filename: str | None = None,
                     source_url: str = "", employee_id: int | None = None, telegram_id: int | None = None,
                     external_user: str = "", folder: str = "", expire_days: int | None = None, password: str = "",
                     caption: str = "", wait: float = 55, idempotency_key: str | None = None) -> UploadResult:
        """Faylni yuklaydi. `wait` soniya ichida tayyor bo'lsa — havola va QR bilan qaytadi; bo'lmasa holat `queued`,
        keyin `wait_ready(id)` yoki webhook orqali natija olinadi."""
        data: dict[str, Any] = {k: v for k, v in {"source_url": source_url, "employee_id": employee_id, "telegram_id": telegram_id,
                                                  "external_user": external_user, "folder": folder, "expire_days": expire_days,
                                                  "password": password, "caption": caption}.items() if v not in (None, "")}
        files = None
        if file is not None:
            if isinstance(file, (str, Path)):
                path = Path(file)
                files = {"file": (filename or path.name, path.read_bytes())}
            elif isinstance(file, bytes):
                files = {"file": (filename or "fayl", file)}
            else:
                files = {"file": (filename or getattr(file, "name", "fayl"), file.read())}
        headers = {"Idempotency-Key": idempotency_key or uuid.uuid4().hex}
        params = {"wait": int(wait)} if wait else {"async": "true"}
        r = await self._request("POST", "/files", data=data, files=files, headers=headers, params=params)
        return UploadResult.from_json(r.json())

    async def get(self, file_id: int) -> UploadResult:
        return UploadResult.from_json((await self._request("GET", f"/files/{file_id}")).json())

    async def wait_ready(self, file_id: int, timeout: float = 300, interval: float = 2) -> UploadResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            res = await self.get(file_id)
            if res.status in ("delivered", "failed") or loop.time() > deadline:
                return res
            await asyncio.sleep(interval)

    async def qr_png(self, file_id: int, size: int | None = None) -> bytes:
        return (await self._request("GET", f"/files/{file_id}/qr.png", params={"size": size} if size else None)).content

    async def refresh_link(self, file_id: int, expire_days: int | None = None, password: str | None = None) -> UploadResult:
        r = await self._request("POST", f"/files/{file_id}/link", json={"expire_days": expire_days, "password": password})
        return UploadResult.from_json(r.json())

    async def revoke_link(self, file_id: int) -> None:
        await self._request("DELETE", f"/files/{file_id}/link")

    async def make_qr(self, url: str, *, size: int | None = None, caption: str = "") -> bytes:
        """Istalgan havoladan QR (PNG)."""
        return (await self._request("POST", "/qr", json={"url": url, "size": size, "caption": caption})).content

    async def employees(self, q: str = "") -> list[dict[str, Any]]:
        return (await self._request("GET", "/employees", params={"q": q} if q else None)).json()
