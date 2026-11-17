"""Panel sozlamalari (.env o'rniga): ommaviy manzil, standart saqlash joyi, eski .env importi, Google OAuth, analitika."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import respx
from sqlalchemy import select

from qrdrive import settings_store
from qrdrive.core.config import config
from qrdrive.db.models import Storage
from qrdrive.db.session import session_scope
from qrdrive.services import system
from qrdrive.storage import registry

from .conftest import auth
from .test_api import process_all


async def test_default_storage_seeded(session, monkeypatch):
    monkeypatch.setattr(config, "seed_default_storage", True)
    await system.seed_default_storage(session)
    st = (await session.execute(select(Storage))).scalar_one()
    cfg = registry.get_config(st)
    assert st.is_primary and st.kind == "synology" and cfg["url"] == "https://file.stargroup.uz"
    assert cfg["drive_folder"].endswith("#file_id=984701843502314054")
    assert st.last_error == "not_configured"
    result = await registry.check(st)  # login/parol yo'q — tarmoqqa chiqmaydi
    assert result["ok"] is False and result["kind"] == "not_configured" and st.status == "unknown"
    await system.seed_default_storage(session)  # takroran yaratilmaydi
    assert len((await session.execute(select(Storage))).scalars().all()) == 1


async def test_public_base_url_from_panel(client, local_storage, employee):
    h = auth("admin")
    r = await client.patch("/qrdrive/api/admin/settings", headers=h, json={"public_base_url": "https://zona.stargroup.uz/"})
    assert r.status_code == 200 and r.json()["public_base_url"] == "https://zona.stargroup.uz/"
    r = await client.post("/qrdrive/api/admin/files/upload", headers=h, data={"employee_id": str(employee.id)},
                          files={"files": ("a.txt", b"a", "text/plain")})
    await process_all()
    f = (await client.get(f"/qrdrive/api/admin/files/{r.json()[0]['id']}", headers=h)).json()
    assert f["url"].startswith("https://zona.stargroup.uz/qrdrive/s/")
    sysinfo = (await client.get("/qrdrive/api/admin/system", headers=h)).json()
    assert sysinfo["runtime"]["public_base_url"] == "https://zona.stargroup.uz"


async def test_legacy_import_from_panel(client):
    env = b"BOT_TOKEN=123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij\nSYNO_URL=https://nas:5001\nSYNO_USER=u\nSYNO_PASS=p\nALLOWED_USER_IDS=1,2\n"
    r = await client.post("/qrdrive/api/admin/system/legacy-import", headers=auth("admin"),
                          files={"file": (".env", env, "text/plain")})
    assert r.status_code == 200 and r.json() == {"ok": True, "employees": 2, "storage": True}
    assert "ABCDEFGHIJ" not in r.text
    bad = await client.post("/qrdrive/api/admin/system/legacy-import", headers=auth("admin"), files={"file": (".env", b"X=1", "text/plain")})
    assert bad.status_code == 400
    async with session_scope() as s:
        assert (await settings_store.load(s, fresh=True))["bot_token"].startswith("123456:")


@respx.mock
async def test_google_oauth_flow(client):
    respx.route(host="testserver").pass_through()
    h = auth("admin")
    r = await client.post("/qrdrive/api/admin/storages", headers=h, json={
        "name": "Drive", "kind": "gdrive", "config": {"auth": "oauth", "client_id": "CID", "client_secret": "CS"}})
    sid = r.json()["id"]
    assert r.json()["config"]["google_connected"] is False
    start = (await client.post(f"/qrdrive/api/admin/storages/{sid}/google/start", headers=h)).json()
    qs = parse_qs(urlsplit(start["url"]).query)
    assert qs["client_id"] == ["CID"] and qs["access_type"] == ["offline"]
    respx.post("https://oauth2.googleapis.com/token").mock(side_effect=[
        httpx.Response(200, json={"refresh_token": "RT", "access_token": "AT"}),
        httpx.Response(200, json={"access_token": "AT2", "expires_in": 3600})])
    respx.get("https://www.googleapis.com/drive/v3/files/root").mock(return_value=httpx.Response(200, json={"id": "root"}))
    respx.get("https://www.googleapis.com/drive/v3/about").mock(return_value=httpx.Response(200, json={"storageQuota": {"limit": "100", "usage": "10"}}))
    bad = await client.get("/qrdrive/api/admin/storages/google/callback", params={"state": "1.1.x", "code": "C"})
    assert bad.status_code in (302, 307) and "google=error" in bad.headers["location"]
    cb = await client.get("/qrdrive/api/admin/storages/google/callback", params={"state": qs["state"][0], "code": "C"})
    assert "google=ok" in cb.headers["location"]
    st = (await client.get("/qrdrive/api/admin/storages", headers=h)).json()[0]
    assert st["config"]["google_connected"] is True and st["status"] == "ok" and st["quota_total"] == 100
    assert "RT" not in str(st)


async def test_analytics(client, local_storage, employee):
    h = auth("admin")
    for name in ("a.pdf", "b.jpg", "c.docx"):
        await client.post("/qrdrive/api/admin/files/upload", headers=h, data={"employee_id": str(employee.id)},
                          files={"files": (name, name.encode(), "application/octet-stream")})
    await process_all()
    d = (await client.get("/qrdrive/api/admin/analytics", headers=auth("viewer"))).json()
    assert d["totals"]["delivered"] == 3 and d["employees"][0]["name"] == "Olimova Dilnoza"
    assert {t["type"] for t in d["types"]} == {"pdf", "image", "doc"}
    assert sum(map(sum, d["heatmap"])) == 3 and len(d["daily"]) == 30
    assert d["departments"][0]["name"] == "Kadrlar" and d["stages"][0]["avg_ms"] is not None
    x = await client.get("/qrdrive/api/admin/analytics/export.xlsx", headers=h)
    assert x.status_code == 200 and x.content[:2] == b"PK"
