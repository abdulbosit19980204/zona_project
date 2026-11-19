"""Asosiy havola — saqlash joyiniki (Synology Drive); muddat/parol so'ralsa qo'shimcha foydali havolasi.
Telegram javoblari foydalanuvchi xabariga reply bo'ladi."""
from __future__ import annotations

import httpx
from sqlalchemy import select

from qrdrive.core.errors import NotSupported
from qrdrive.db.models import FileRecord, SystemLink
from qrdrive.services import files as files_svc
from qrdrive.services.telegram import TelegramClient
from qrdrive.storage.base import PublicLink

from .conftest import auth

NAS = "https://file.stargroup.uz/d/s/ORIG/TOKEN"


class DriveLike:
    """Synology Drive kabi: o'z havolasini beradi, lekin muddat/parolni qo'llamaydi."""
    supports_links = True

    def __init__(self):
        self.calls = []

    async def create_public_link(self, remote, expires_at=None, password=None, visibility="public"):
        self.calls.append((expires_at, password))
        if expires_at or password:
            raise NotSupported("Drive: muddat/parol yo'q")
        return PublicLink(url=NAS, id="drive:1", visibility=visibility)

    async def close(self):
        pass


async def _delivered(session, local_storage, **opts) -> FileRecord:
    local_storage.link_mode = "provider"
    rec = FileRecord(source="telegram", original_name="a.rar", status="delivered", storage_id=local_storage.id,
                     remote_path="/Kadrlar/a.rar", remote_id="/Kadrlar/a.rar", kind="file", options=opts)
    session.add(rec)
    await session.commit()
    await session.refresh(rec, ["storage"])
    return rec


async def test_protected_link_keeps_storage_link_and_adds_extra(session, local_storage):
    rec = await _delivered(session, local_storage, expire_days=60, password_enc=files_svc.encrypt("p1"))
    url = await files_svc.create_link(session, rec, rec.storage, DriveLike(), {})
    await session.commit()
    assert url == NAS and rec.link_kind == "provider" and not rec.link_has_password and rec.link_expires_at is None
    extra = await files_svc.extra_links(session, rec, "https://foydali.xisobchim.uz")
    assert len(extra) == 1 and extra[0]["has_password"] and extra[0]["expires_at"] is not None
    assert extra[0]["url"].startswith("https://foydali.xisobchim.uz/qrdrive/s/")


async def test_plain_link_has_no_extra(session, local_storage):
    rec = await _delivered(session, local_storage)
    assert await files_svc.create_link(session, rec, rec.storage, DriveLike(), {}) == NAS
    await session.commit()
    assert await files_svc.extra_links(session, rec) == []


async def test_relink_repairs_system_link_and_keeps_old_one(session, local_storage, monkeypatch):
    """Avval tizim havolasiga tushib qolgan fayl: asosiy havola NAS'niki bo'ladi, eski foydali havolasi (QR) ishlayveradi."""
    rec = await _delivered(session, local_storage, expire_days=60, password_enc=files_svc.encrypt("p1"))
    old = await files_svc.create_system_link(session, rec, None, "p1", "https://foydali.xisobchim.uz")
    old_token = rec.link_id
    await session.commit()
    monkeypatch.setattr(files_svc.registry, "build", lambda st: DriveLike())
    result = await files_svc.relink(session, [rec], {})
    await session.commit()
    assert result["done"] == 1 and rec.link_url == NAS and rec.link_kind == "provider"
    links = (await session.execute(select(SystemLink).where(SystemLink.file_id == rec.id))).scalars().all()
    assert [lk.token for lk in links] == [old_token] and not links[0].revoked  # yangi nusxa yaratilmadi
    assert [e["url"] for e in await files_svc.extra_links(session, rec, "https://foydali.xisobchim.uz")] == [old]


async def test_refresh_with_password_via_api(client, session, local_storage, monkeypatch):
    rec = await _delivered(session, local_storage)
    monkeypatch.setattr(files_svc.registry, "build", lambda st: DriveLike())
    r = await client.post(f"/qrdrive/api/admin/files/{rec.id}/link", json={"expire_days": 60, "password": "x"}, headers=auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == NAS and body["link_kind"] == "provider"
    assert len(body["extra_links"]) == 1 and body["extra_links"][0]["has_password"]


async def test_extra_link_api_create_list_revoke(client, session, local_storage):
    rec = await _delivered(session, local_storage)
    rec.link_url, rec.link_id, rec.link_kind = NAS, "drive:1", "provider"
    await session.commit()
    r = await client.post(f"/qrdrive/api/admin/files/{rec.id}/extra-link", json={"expire_days": 7}, headers=auth())
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert "/qrdrive/s/" in r.json()["url"] and len(r.json()["extra_links"]) == 1
    detail = (await client.get(f"/qrdrive/api/admin/files/{rec.id}", headers=auth())).json()
    assert detail["url"] == NAS and [e["token"] for e in detail["extra_links"]] == [token]
    r = await client.delete(f"/qrdrive/api/admin/files/{rec.id}/extra-link/{token}", headers=auth())
    assert r.status_code == 200 and r.json()["extra_links"] == []
    assert (await client.delete(f"/qrdrive/api/admin/files/{rec.id}/extra-link/nope", headers=auth())).status_code == 404
    viewer = await client.post(f"/qrdrive/api/admin/files/{rec.id}/extra-link", json={}, headers=auth("viewer"))
    assert viewer.status_code == 403


async def test_telegram_reply_parameters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8", "replace")
        seen[request.url.path.rsplit("/", 1)[-1]] = body
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    tg = TelegramClient("T", transport=httpx.MockTransport(handler))
    await tg.send_photo(1, b"png", "cap", reply_to=42)
    await tg.send_message(1, "hi", reply_to=None)
    await tg.close()
    assert '"message_id": 42' in seen["sendPhoto"] and "allow_sending_without_reply" in seen["sendPhoto"]
    assert "reply_parameters" not in seen["sendMessage"]
