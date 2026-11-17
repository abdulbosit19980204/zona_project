"""Qabul mezoni 7: boshqa loyiha SDK orqali QR funksiyasini oladi (haqiqiy API ilovasiga qarshi)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

from qrdrive.main import app

from .conftest import auth
from .test_api import process_all

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))
from qrdrive_sdk import QRDriveClient, QRDriveError  # noqa: E402


async def test_sdk_upload_and_qr(client, local_storage):
    r = await client.post("/qrdrive/api/admin/api-keys", headers=auth("admin"), json={"name": "boshqa loyiha"})
    key = r.json()["key"]
    sdk = QRDriveClient("http://testserver", key, transport=httpx.ASGITransport(app=app))

    async def worker():  # worker o'rnida: navbatni ishlab beradi
        for _ in range(40):
            await process_all()
            await asyncio.sleep(0.1)

    task = asyncio.create_task(worker())
    res = await sdk.upload(b"salom dunyo", filename="xat.txt", external_user="hr-bot", wait=10)
    await task
    assert res.ready and res.url and res.qr_png[:4] == b"\x89PNG"
    assert (await sdk.get(res.id)).url == res.url
    assert (await sdk.qr_png(res.id))[:4] == b"\x89PNG"
    assert (await sdk.make_qr("https://example.com"))[:4] == b"\x89PNG"
    try:
        await sdk.employees()
    except QRDriveError as e:
        assert e.status == 403  # scope berilmagan
    else:
        raise AssertionError("scope tekshirilmadi")
    await sdk.close()
