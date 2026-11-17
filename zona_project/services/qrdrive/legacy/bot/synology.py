"""Synology DSM File Station API bilan ishlash (login, yuklash, ommaviy havola)."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import aiohttp

log = logging.getLogger(__name__)

# Sessiya eskirgan / yaroqsiz bo'lganda qaytadigan xato kodlari
_RELOGIN_CODES = {105, 106, 107, 119}


class SynologyError(Exception):
    pass


class Synology:
    def __init__(self, base_url: str, user: str, password: str, verify_ssl: bool = True):
        self.base = base_url.rstrip("/")
        self.url = f"{self.base}/webapi/entry.cgi"
        self.user = user
        self.password = password
        self.verify_ssl = verify_ssl
        self.sid: str | None = None
        self._session: aiohttp.ClientSession | None = None

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=None if self.verify_ssl else False)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=900),  # 100 MB yuklash uchun yetarli vaqt
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> None:
        data = await self._call(
            {
                "api": "SYNO.API.Auth",
                "version": "6",
                "method": "login",
                "account": self.user,
                "passwd": self.password,
                "session": "FileStation",
                "format": "sid",
            },
            auth=False,
        )
        self.sid = data["sid"]
        log.info("Synology'ga kirildi")

    async def _call(self, params: dict, auth: bool = True, retry: bool = True) -> dict:
        if auth and not self.sid:
            await self.login()
        query = {**params, "_sid": self.sid} if auth else params
        s = await self._http()
        async with s.get(self.url, params=query) as r:
            r.raise_for_status()
            body = await r.json(content_type=None)
        if body.get("success"):
            return body.get("data") or {}
        code = (body.get("error") or {}).get("code")
        if auth and retry and code in _RELOGIN_CODES:
            self.sid = None
            return await self._call(params, auth=True, retry=False)
        raise SynologyError(f"{params.get('api')}.{params.get('method')} xato kodi: {code}")

    async def upload(self, local_path: str, dest_folder: str, filename: str) -> str:
        """Faylni dest_folder ichiga yuklaydi (papka bo'lmasa yaratiladi). To'liq yo'lni qaytaradi."""
        for attempt in (1, 2):
            if not self.sid:
                await self.login()
            s = await self._http()
            # quote_fields=False: kirill/o'zbek harfli fayl nomlari buzilmasligi uchun
            form = aiohttp.FormData(quote_fields=False)
            form.add_field("path", dest_folder)
            form.add_field("create_parents", "true")
            form.add_field("overwrite", "true")
            with open(local_path, "rb") as f:
                # Synology talabi: fayl maydoni eng oxirida bo'lishi kerak
                form.add_field("file", f, filename=filename, content_type="application/octet-stream")
                async with s.post(
                    self.url,
                    params={"api": "SYNO.FileStation.Upload", "version": "2", "method": "upload", "_sid": self.sid},
                    data=form,
                ) as r:
                    r.raise_for_status()
                    body = await r.json(content_type=None)
            if body.get("success"):
                return f"{dest_folder.rstrip('/')}/{filename}"
            code = (body.get("error") or {}).get("code")
            if attempt == 1 and code in _RELOGIN_CODES:
                self.sid = None
                continue
            raise SynologyError(f"Upload xato kodi: {code}, javob: {body}")
        raise SynologyError("Upload muvaffaqiyatsiz")

    async def share(self, path: str, expire_days: int = 0, password: str = "") -> str:
        """Fayl uchun ommaviy havola yaratadi va URL'ni qaytaradi."""
        params = {
            "api": "SYNO.FileStation.Sharing",
            "version": "3",
            "method": "create",
            "path": json.dumps([path], ensure_ascii=False),
        }
        if expire_days > 0:
            params["date_expired"] = (date.today() + timedelta(days=expire_days)).isoformat()
        if password:
            params["password"] = password
        data = await self._call(params)
        links = data.get("links") or []
        if not links or not links[0].get("url"):
            raise SynologyError(f"Havola qaytmadi: {data}")
        return links[0]["url"]
