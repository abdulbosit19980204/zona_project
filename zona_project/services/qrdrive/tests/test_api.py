"""API: SSO va rollar, admin endpointlar, tashqi API v1 (kalit, scope, idempotency), webhook imzosi, tizim havolasi."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx
import respx
from sqlalchemy import select

from qrdrive.core.logging import mask
from qrdrive.db.models import AuditLog, FileRecord, Setting, WebhookDelivery
from qrdrive.db.session import session_scope
from qrdrive.services import pipeline
from qrdrive.worker.main import Worker

from .conftest import auth, sso_token


async def process_all():
    while True:
        async with session_scope() as s:
            fid = await pipeline.claim_next(s)
        if fid is None:
            return
        async with session_scope() as s:
            await pipeline.process(s, fid)


async def test_sso_required_and_roles(client):
    assert (await client.get("/qrdrive/api/admin/dashboard")).status_code == 401
    expired = {"Authorization": f"Bearer {sso_token(exp=-10)}"}
    assert (await client.get("/qrdrive/api/admin/dashboard", headers=expired)).status_code == 401
    refresh = {"Authorization": f"Bearer {sso_token(token_type='refresh')}"}
    assert (await client.get("/qrdrive/api/admin/dashboard", headers=refresh)).status_code == 401
    assert (await client.get("/qrdrive/api/admin/dashboard", headers=auth("viewer"))).status_code == 200
    r = await client.patch("/qrdrive/api/admin/settings", json={"max_file_mb": 50}, headers=auth("editor"))
    assert r.status_code == 403 and "Superadmin" in r.json()["detail"]
    r = await client.post("/qrdrive/api/admin/employees", json={"full_name": "A"}, headers=auth("viewer"))
    assert r.status_code == 403


async def test_settings_secret_never_returned(client):
    r = await client.patch("/qrdrive/api/admin/settings", json={"link_password": "sir123", "max_file_mb": 50},
                           headers=auth("admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["link_password_set"] is True and "link_password" not in body and "sir123" not in r.text
    r = await client.get("/qrdrive/api/admin/settings", headers=auth())
    assert "sir123" not in r.text
    async with session_scope() as s:
        log = (await s.execute(select(AuditLog).where(AuditLog.action == "settings.update"))).scalar_one()
        assert "sir123" not in json.dumps(log.details)
        assert "sir123" not in ((await s.get(Setting, "link_password")).secret_enc)


async def test_bad_template_rejected(client):
    r = await client.patch("/qrdrive/api/admin/settings", json={"folder_template": "{nomalum}/x"}, headers=auth("admin"))
    assert r.status_code == 400


async def test_full_admin_flow(client, storage_root):
    h = auth("admin")
    r = await client.post("/qrdrive/api/admin/storages", headers=h, json={
        "name": "Disk", "kind": "local", "base_folder": "Kadrlar", "config": {"root": str(storage_root)}})
    assert r.status_code == 200, r.text
    assert r.json()["check"]["ok"] and r.json()["is_primary"] and r.json()["link_mode"] == "system"
    r = await client.post("/qrdrive/api/admin/employees", headers=h, json={"full_name": "Karimov Bobur", "department": "Kadrlar"})
    emp = r.json()
    assert emp["folder"] == "Karimov Bobur"
    r = await client.post("/qrdrive/api/admin/files/upload", headers=h, data={"employee_id": str(emp["id"])},
                          files={"files": ("buyruq.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 200, r.text
    fid = r.json()[0]["id"]
    await process_all()
    r = await client.get(f"/qrdrive/api/admin/files/{fid}", headers=h)
    f = r.json()
    assert f["status"] == "delivered" and len(f["events"]) == 6
    assert (await client.get(f"/qrdrive/api/admin/files/{fid}/content", headers=h)).content == b"%PDF-1.4 test"
    png = await client.get(f"/qrdrive/api/admin/files/{fid}/qr.png", headers=h)
    assert png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    assert (await client.get(f"/qrdrive/api/admin/files/{fid}/qr.pdf", headers=h)).content[:4] == b"%PDF"
    # tizim havolasi ochiladi va yuklab olishlar sanaladi
    url = f["url"].replace("http://testserver", "")
    assert (await client.get(url)).content == b"%PDF-1.4 test"
    # parol bilan yangilash
    r = await client.post(f"/qrdrive/api/admin/files/{fid}/link", headers=h, json={"password": "777", "expire_days": 3})
    new_url = r.json()["url"].replace("http://testserver", "")
    assert new_url != url and r.json()["has_password"] and r.json()["expires_at"]
    assert (await client.get(url)).status_code == 404  # eski havola bekor
    form = await client.get(new_url)
    assert form.status_code == 200 and "parol" in form.text.lower()
    assert (await client.post(new_url, data={"password": "x"})).status_code == 401
    assert (await client.post(new_url, data={"password": "777"})).content == b"%PDF-1.4 test"
    # papka brauzeri
    folders = (await client.get("/qrdrive/api/admin/files/folders", headers=h)).json()
    assert folders[0]["count"] == 1
    (storage_root / "Kadrlar" / "Karimov Bobur" / "qolda.txt").write_text("tashqi")
    browse = (await client.get("/qrdrive/api/admin/files/browse", headers=h,
                               params={"storage_id": 1, "path": "/Kadrlar/Karimov Bobur"})).json()
    flags = {e["name"]: e["registered"] for e in browse["entries"]}
    assert flags["qolda.txt"] is False and sum(flags.values()) == 1
    # nomini o'zgartirish, savat, tiklash, butunlay o'chirish
    r = await client.post(f"/qrdrive/api/admin/files/{fid}/rename", headers=h, json={"name": "yangi.pdf"})
    assert r.json()["remote_path"].endswith("/yangi.pdf")
    assert (await client.delete(f"/qrdrive/api/admin/files/{fid}", headers=h)).status_code == 200
    trash = (await client.get("/qrdrive/api/admin/files", headers=h, params={"trash": True})).json()
    assert trash["total"] == 1
    assert (await client.delete(f"/qrdrive/api/admin/files/{fid}/purge", headers=h)).status_code == 200
    assert not (storage_root / "Kadrlar" / "Karimov Bobur" / "yangi.pdf").exists()
    # boshqa sahifalar
    for path in ("dashboard", "errors", "audit", "system", "setup", "notifications", "storages/kinds", "requests",
                 "employees", "departments", "api-keys/scopes"):
        r = await client.get(f"/qrdrive/api/admin/{path}", headers=h)
        assert r.status_code == 200, (path, r.text)
    d = (await client.get("/qrdrive/api/admin/dashboard", headers=h)).json()
    assert d["kpi"]["total"] == 0 and len(d["daily"]) == 30
    assert (await client.post("/qrdrive/api/admin/system/backup", headers=auth("admin"))).status_code == 200


async def test_employee_import_and_invite(client):
    h = auth("admin")
    csv_data = "F.I.Sh.;Bo'lim;Lavozim;Telefon\nAliyev Sardor;Kadrlar;Inspektor;+998901112233\nKarimova Laylo;Buxgalteriya;;\n"
    r = await client.post("/qrdrive/api/admin/employees/import", headers=h,
                          files={"file": ("xodimlar.csv", csv_data.encode(), "text/csv")})
    assert r.json() == {"created": 2, "updated": 0, "total": 2}
    emps = (await client.get("/qrdrive/api/admin/employees", headers=h)).json()
    assert {e["department"] for e in emps} == {"Kadrlar", "Buxgalteriya"}
    r = await client.post(f"/qrdrive/api/admin/employees/{emps[0]['id']}/invite", headers=h, json={})
    assert r.json()["code"] and r.json()["bot_missing"] is True
    xlsx = await client.get("/qrdrive/api/admin/employees/export.xlsx", headers=h)
    assert xlsx.content[:2] == b"PK"


async def _api_key(client, scopes=("files:write", "files:read", "qr:generate"), webhook: str = "") -> dict:
    r = await client.post("/qrdrive/api/admin/api-keys", headers=auth("admin"),
                          json={"name": "HR bot", "scopes": list(scopes), "webhook_url": webhook})
    assert r.status_code == 200, r.text
    return r.json()


async def test_api_v1_flow(client, local_storage, employee):
    key = await _api_key(client)
    assert key["key"].startswith("qd_live_")
    keys = (await client.get("/qrdrive/api/admin/api-keys", headers=auth())).json()
    assert "key" not in keys[0] and key["key"] not in json.dumps(keys)  # kalit faqat bir marta
    h = {"Authorization": f"Bearer {key['key']}", "Idempotency-Key": "req-1"}
    r = await client.post("/qrdrive/api/v1/files?async=true", headers=h, data={"employee_id": str(employee.id)},
                          files={"file": ("hujjat.docx", b"docx-bytes", "application/octet-stream")})
    assert r.status_code == 202, r.text
    fid = r.json()["id"]
    again = await client.post("/qrdrive/api/v1/files?async=true", headers=h, data={"employee_id": str(employee.id)},
                              files={"file": ("hujjat.docx", b"docx-bytes", "application/octet-stream")})
    assert again.json()["id"] == fid  # Idempotency-Key
    await process_all()
    r = await client.get(f"/qrdrive/api/v1/files/{fid}", headers={"Authorization": h["Authorization"]})
    body = r.json()
    assert body["status"] == "delivered" and body["url"] and body["qr_base64"]
    qr = await client.post("/qrdrive/api/v1/qr", headers={"Authorization": h["Authorization"]},
                           json={"url": "https://example.com", "format": "base64"})
    assert qr.json()["qr_base64"]
    # scope yo'q
    r = await client.get("/qrdrive/api/v1/employees", headers={"Authorization": h["Authorization"]})
    assert r.status_code == 403
    # noto'g'ri kalit
    assert (await client.get("/qrdrive/api/v1/files", headers={"Authorization": "Bearer qd_live_xxx"})).status_code == 401
    # bekor qilingan kalit
    await client.delete(f"/qrdrive/api/admin/api-keys/{key['id']}", headers=auth("admin"))
    assert (await client.get("/qrdrive/api/v1/files", headers={"Authorization": h["Authorization"]})).status_code == 401
    assert (await client.get("/qrdrive/api/v1/health")).json()["ok"]


async def test_api_v1_ip_and_rate_limit(client, local_storage):
    key = await _api_key(client)
    await client.patch(f"/qrdrive/api/admin/api-keys/{key['id']}", headers=auth("admin"),
                       json={"allowed_ips": ["10.0.0.0/8"], "rate_limit": 2})
    h = {"Authorization": f"Bearer {key['key']}"}
    assert (await client.get("/qrdrive/api/v1/files", headers=h)).status_code == 403
    await client.patch(f"/qrdrive/api/admin/api-keys/{key['id']}", headers=auth("admin"), json={"allowed_ips": []})
    codes = [(await client.get("/qrdrive/api/v1/files", headers=h)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


@respx.mock
async def test_webhook_signature(respx_mock, client, local_storage):
    route = respx_mock.post("https://hooks.example.com/qr").mock(return_value=httpx.Response(200))
    key = await _api_key(client, webhook="https://hooks.example.com/qr")
    secret = key["webhook_secret"]
    h = {"Authorization": f"Bearer {key['key']}"}
    r = await client.post("/qrdrive/api/v1/files?async=true", headers=h, data={"external_user": "boshqa-bot"},
                          files={"file": ("a.txt", b"abc", "text/plain")})
    assert r.status_code == 202
    await process_all()
    await Worker().webhooks()
    assert route.called
    req = route.calls.last.request
    expected = "sha256=" + hmac.new(secret.encode(), req.content, hashlib.sha256).hexdigest()
    assert req.headers["X-QRDrive-Signature"] == expected
    payload = json.loads(req.content)
    assert payload["event"] == "file.completed" and payload["file"]["url"]
    async with session_scope() as s:
        d = (await s.execute(select(WebhookDelivery))).scalar_one()
        assert d.status == "ok"
        rec = await s.get(FileRecord, r.json()["id"])
        assert "/boshqa-bot/" in rec.remote_path


def test_log_masking(caplog):
    text = ("token=123456789:AAH-abcdefghijklmnopqrstuvwxyz0123 password=Sir_123 "
            "Authorization: Bearer abc.def key qd_live_ABCDEF https://api.telegram.org/bot123456789:AAH-abcdefghijklmnopqrstuvwxyz0123/getMe")
    out = mask(text)
    for secret in ("AAH-abcdefghijklmnopqrstuvwxyz0123", "Sir_123", "abc.def", "qd_live_ABCDEF"):
        assert secret not in out
    logging.getLogger("x").info(text)
