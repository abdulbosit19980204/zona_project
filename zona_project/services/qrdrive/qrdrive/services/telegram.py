"""Telegram Bot API ga yengil HTTP klient (worker va API shu bilan xabar yuboradi; bot jarayoni — aiogram).
Lokal Bot API server (2 GB gacha) ham qo'llab-quvvatlanadi."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import httpx

from ..core.errors import TelegramError

OFFICIAL = "https://api.telegram.org"


class TelegramClient:
    def __init__(self, token: str, api_url: str = "", local: bool = False, transport: httpx.AsyncBaseTransport | None = None):
        if not token:
            raise TelegramError("Bot tokeni kiritilmagan")
        self.token = token
        self.base = (api_url or OFFICIAL).rstrip("/")
        self.local = local and bool(api_url)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=15), transport=transport)

    @classmethod
    def from_settings(cls, s: dict[str, Any]) -> TelegramClient:
        return cls(s.get("bot_token", ""), s.get("bot_api_url", ""), bool(s.get("bot_api_local")))

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> TelegramClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def call(self, method: str, data: dict[str, Any] | None = None, files: dict | None = None) -> Any:
        url = f"{self.base}/bot{self.token}/{method}"
        payload = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                   for k, v in (data or {}).items() if v is not None}
        try:
            r = await self._client.post(url, data=payload, files=files)
        except httpx.HTTPError as e:
            raise TelegramError(f"{method}: {type(e).__name__}") from e
        try:
            body = r.json()
        except ValueError as e:
            raise TelegramError(f"{method}: HTTP {r.status_code}") from e
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', r.status_code)}")
        return body.get("result")

    async def get_me(self) -> dict[str, Any]:
        return await self.call("getMe")

    async def download(self, file_id: str, dest: Path) -> tuple[Path, bool]:
        """Faylni oladi. (yo'l, vaqtinchami) — lokal serverda fayl diskda bo'lsa, nusxa olinmaydi."""
        info = await self.call("getFile", {"file_id": file_id})
        file_path = info.get("file_path") or ""
        if self.local and os.path.isabs(file_path) and os.path.exists(file_path):
            shutil.copyfile(file_path, dest)
            return dest, True
        url = f"{self.base}/file/bot{self.token}/{file_path}"
        async with self._client.stream("GET", url) as r:
            if r.status_code != 200:
                raise TelegramError(f"download HTTP {r.status_code}")
            with open(dest, "wb") as fh:
                async for chunk in r.aiter_bytes(256 * 1024):
                    fh.write(chunk)
        return dest, True

    @staticmethod
    def _reply(reply_to: int | None) -> dict | None:
        # foydalanuvchi xabariga javob (reply) — asl xabar o'chirilgan bo'lsa ham yuboriladi
        return {"message_id": int(reply_to), "allow_sending_without_reply": True} if reply_to else None

    async def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None, reply_to: int | None = None) -> dict:
        return await self.call("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": reply_markup,
                                               "disable_web_page_preview": "true", "reply_parameters": self._reply(reply_to)})

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            await self.call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})
        except TelegramError:
            pass  # xabar o'chirilgan yoki o'zgarmagan — muhim emas

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self.call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        except TelegramError:
            pass

    async def send_photo(self, chat_id: int, photo: bytes, caption: str = "", reply_markup: dict | None = None,
                         reply_to: int | None = None) -> dict:
        return await self.call("sendPhoto", {"chat_id": chat_id, "caption": caption[:1024], "reply_markup": reply_markup,
                                             "reply_parameters": self._reply(reply_to)},
                               files={"photo": ("qr.png", photo, "image/png")})

    async def send_document(self, chat_id: int, data: bytes, filename: str, caption: str = "") -> dict:
        return await self.call("sendDocument", {"chat_id": chat_id, "caption": caption[:1024]},
                               files={"document": (filename, data, "application/octet-stream")})

    async def log_out(self) -> None:
        await self.call("logOut")
