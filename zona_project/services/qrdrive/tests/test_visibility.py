"""Havola turi (public/private), Synology Drive havolalari, fayl nomi (asl nom boshida)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from qrdrive import settings_store
from qrdrive.core.errors import NotSupported
from qrdrive.db.models import FileRecord, Setting
from qrdrive.db.session import session_scope
from qrdrive.services import pipeline
from qrdrive.services.files import enqueue
from qrdrive.services.naming import render_filename
from qrdrive.storage.base import RemoteFile
from qrdrive.storage.synology import SynologyProvider, filestation_to_drive
from qrdrive.worker.main import Worker

from .conftest import auth
from .test_pipeline import make_temp, run

URL = "https://file.stargroup.uz"


def test_original_name_first_extension_last():
    at = datetime(2026, 11, 17, 18, 8, 21)
    assert render_filename("{asl_nom}_{sana}_{vaqt}", "rasm_20261117.jpg", "x", at) == "rasm_20261117_2026-11-17_18-08-21.jpg"
    assert render_filename("{asl_nom}_{sana}_{vaqt}", "3.4.6-3.4.7.xlsx", "x", at) == "3.4.6-3.4.7_2026-11-17_18-08-21.xlsx"
    assert render_filename("{asl_nom}_{sana}", "README", "x", at) == "README_2026-11-17"
    assert render_filename("{sana}_{vaqt}_{asl_nom}", "Ариза.pdf", "x", at) == "2026-11-17_18-08-21_Ариза.pdf"


async def test_old_default_template_migrated(session):
    session.add(Setting(key="filename_template", value="{sana}_{vaqt}_{asl_nom}"))
    await session.commit()
    assert (await settings_store.load(session, fresh=True))["filename_template"] == "{asl_nom}_{sana}_{vaqt}"


def test_filestation_to_drive():
    assert filestation_to_drive("/Timur/qrable/a.jpg") == "/team-folders/Timur/qrable/a.jpg"
    assert filestation_to_drive("/home/x/a.jpg") == "/mydrive/x/a.jpg"


def drive_fake(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        p = dict(request.url.params)
        if request.method == "POST":
            p.update(dict(httpx.QueryParams(request.content.decode())))
        api = p.get("api")
        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "S"}})
        if api == "SYNO.SynologyDrive.Files":
            assert json.loads(p["path"]) == "/team-folders/Timur/qrable/a/x.jpg"
            state["gets"] = state.get("gets", 0) + 1
            if state["gets"] < 3:  # Drive hali indekslamagan
                return httpx.Response(200, json={"success": False, "error": {"code": 1003}})
            return httpx.Response(200, json={"success": True, "data": {"file_id": "98470", "permanent_link": "1AjyPERM"}})
        if api == "SYNO.SynologyDrive.AdvanceSharing":
            assert p["method"] == "create" and json.loads(p["path"]) == "id:98470"
            return httpx.Response(200, json={"success": True, "data": {"url": f"{URL}/d/s/1AjyPERM/TOKEN", "sharing_link": "TOKEN"}})
        return httpx.Response(200, json={"success": True, "data": {}})
    return handler


@respx.mock
async def test_synology_drive_public_and_private_links():
    state: dict = {}
    respx.route(url__startswith=f"{URL}/webapi/").mock(side_effect=drive_fake(state))
    p = SynologyProvider(URL, "caspar", "x", drive_links=True)
    p.drive_wait = 10
    remote = RemoteFile(path="/Timur/qrable/a/x.jpg")
    pub = await p.create_public_link(remote, visibility="public")
    assert pub.url == f"{URL}/d/s/1AjyPERM/TOKEN" and pub.visibility == "public" and state["gets"] == 3
    priv = await p.create_public_link(remote, visibility="private")
    assert priv.url == f"{URL}/d/f/1AjyPERM" and priv.visibility == "private"
    with pytest.raises(NotSupported):  # muddatli public — Drive API qo'llamaydi -> tizim havolasiga o'tiladi
        await p.create_public_link(remote, datetime.now(timezone.utc) + timedelta(days=3), visibility="public")
    await p.close()


async def test_awaiting_not_processed_until_choice_then_timeout(session, local_storage, employee):
    path, size = make_temp(b"tg")
    rec = await enqueue(session, source="web", original_name="a.txt", employee_id=employee.id, temp_path=path, size=size, awaiting=True)
    await session.commit()
    async with session_scope() as s:
        assert await pipeline.claim_next(s) is None  # tanlov kutilmoqda
    async with session_scope() as s:
        r = await s.get(FileRecord, rec.id)
        r.created_at = datetime.now(timezone.utc) - timedelta(minutes=11)
        await s.commit()
    await settings_store.save(session, {"default_visibility": "private"})
    await Worker().maintenance()
    async with session_scope() as s:
        r = await s.get(FileRecord, rec.id)
        assert r.status == "queued" and r.options["visibility"] == "private"
    done = await run(rec.id)
    # lokal disk private havola bera olmaydi -> tizim havolasi (public)
    assert done.status == "delivered" and done.link_visibility == "public" and "/qrdrive/s/" in done.link_url


async def test_web_upload_visibility_param(client, local_storage, employee):
    r = await client.post("/qrdrive/api/admin/files/upload", headers=auth("admin"),
                          data={"employee_id": str(employee.id), "visibility": "private"},
                          files={"files": ("a.txt", b"a", "text/plain")})
    async with session_scope() as s:
        rec = (await s.execute(select(FileRecord).where(FileRecord.id == r.json()[0]["id"]))).scalar_one()
        assert rec.options["visibility"] == "private" and rec.status == "queued"
