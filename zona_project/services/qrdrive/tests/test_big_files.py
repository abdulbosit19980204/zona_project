"""20 MB dan katta fayllar: rasmiy Bot API bermaydi -> bot bir martalik veb-yuklash havolasini beradi."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from qrdrive import settings_store
from qrdrive.bot.main import BotService
from qrdrive.db.models import FileRecord, TgAccount, UploadTicket
from qrdrive.db.session import session_scope
from qrdrive.services import uploads

from .test_bot import feed, update

MB = 1024 * 1024


def test_bot_can_download():
    assert uploads.bot_can_download(19 * MB, {})
    assert not uploads.bot_can_download(21 * MB, {})
    assert uploads.bot_can_download(None, {})  # hajm noma'lum — urinib ko'riladi
    assert uploads.bot_can_download(500 * MB, {"bot_api_url": "http://127.0.0.1:8081"})  # lokal server


async def test_big_file_gets_upload_link(session, employee):
    session.add(TgAccount(telegram_id=801, username="katta", employee_id=employee.id, status="active"))
    await session.commit()
    s = await feed(BotService(), update(801, "katta", document={"file_id": "BIG", "file_unique_id": "UB",
                                                                "file_name": "video.mp4", "file_size": 45 * MB}))
    msg = next(d for n, d in s.sent if n == "SendMessage")
    assert "20 MB" in msg["text"] and "/qrdrive/u/" in msg["text"]
    assert msg["reply_markup"]["inline_keyboard"][0][0]["url"].endswith(msg["text"].rsplit("/u/", 1)[1])
    async with session_scope() as db:
        assert (await db.execute(select(FileRecord))).first() is None  # navbatga qo'yilmadi (yuklab olib bo'lmaydi)
        ticket = (await db.execute(select(UploadTicket))).scalar_one()
        assert ticket.name == "video.mp4" and ticket.size == 45 * MB and ticket.chat_id == 801


async def _ticket(session, employee, tid: int) -> UploadTicket:
    acc = TgAccount(telegram_id=tid, username=f"u{tid}", employee_id=employee.id, status="active")
    session.add(acc)
    await session.flush()
    ticket = await uploads.create_ticket(session, acc, tid, "hisobot.zip", 30 * MB, "izoh")
    await session.commit()
    return ticket


async def test_web_upload_flow(client, session, employee):
    ticket = await _ticket(session, employee, 802)
    url = f"/qrdrive/u/{ticket.token}"
    page = await client.get(url)
    assert page.status_code == 200 and "hisobot.zip" in page.text and "data-max" in page.text
    data = os.urandom(2 * MB)
    r = await client.post(url, content=data, headers={"X-File-Name": "hisobot%202026.zip", "X-Visibility": "private"})
    assert r.status_code == 200 and r.json()["ok"]
    async with session_scope() as db:
        rec = await db.get(FileRecord, r.json()["id"])
        assert (rec.status, rec.original_name, rec.size, rec.tg_chat_id, rec.caption) == ("queued", "hisobot 2026.zip", len(data), 802, "izoh")
        assert rec.options["visibility"] == "private" and Path(rec.temp_path).read_bytes() == data
        Path(rec.temp_path).unlink()
    again = await client.post(url, content=b"x", headers={"X-File-Name": "b.txt"})
    assert again.status_code == 410  # bir martalik
    assert (await client.get(url)).status_code == 410


async def test_web_upload_limits(client, session, employee):
    await settings_store.save(session, {"max_file_mb": 1})
    ticket = await _ticket(session, employee, 803)
    url = f"/qrdrive/u/{ticket.token}"
    r = await client.post(url, content=os.urandom(MB + 10), headers={"X-File-Name": "a.bin"})
    assert r.status_code == 413
    assert (await client.get("/qrdrive/u/yoq-token")).status_code == 410
    async with session_scope() as db:
        t = await db.get(UploadTicket, ticket.token)
        assert t.used_at is None  # muvaffaqiyatsiz urinish havolani yoqmaydi
        t.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()
    assert (await client.get(url)).status_code == 410  # muddati tugagan
