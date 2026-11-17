"""Synology provayderi — soxta DSM server (respx) bilan."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from qrdrive.core.errors import StorageAuthError, StorageQuota
from qrdrive.storage.base import RemoteFile
from qrdrive.storage.synology import SynologyProvider

URL = "https://nas.local:5001"
ENTRY = f"{URL}/webapi/entry.cgi"


def fake_dsm(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if request.method == "POST" and request.headers.get("content-type", "").startswith("application/x-www-form"):
            params.update(dict(httpx.QueryParams(request.content.decode())))
        api, method = params.get("api"), params.get("method")
        state.setdefault("calls", []).append(f"{api}.{method}")
        if api == "SYNO.API.Auth":
            if params.get("passwd") != "right":
                return httpx.Response(200, json={"success": False, "error": {"code": 400}})
            state["logins"] = state.get("logins", 0) + 1
            return httpx.Response(200, json={"success": True, "data": {"sid": f"sid{state['logins']}"}})
        if params.get("_sid") != f"sid{state.get('logins', 0)}" or state.pop("expire", False):
            return httpx.Response(200, json={"success": False, "error": {"code": 119}})
        if api == "SYNO.FileStation.Upload":
            if state.get("full"):
                return httpx.Response(200, json={"success": False, "error": {"code": 416}})
            body = request.content
            state["uploaded"] = "Ариза.pdf".encode() in body
            return httpx.Response(200, json={"success": True, "data": {}})
        if api == "SYNO.FileStation.Sharing" and method == "create":
            return httpx.Response(200, json={"success": True, "data": {"links": [{"id": "L1", "url": "https://gofile.me/abc"}]}})
        if api == "SYNO.FileStation.List" and method == "list_share":
            return httpx.Response(200, json={"success": True, "data": {"shares": [
                {"path": "/Kadrlar", "additional": {"volume_status": {"totalspace": 1000, "freespace": 50}}}]}})
        return httpx.Response(200, json={"success": True, "data": {}})
    return handler


@respx.mock
async def test_upload_and_share(tmp_path: Path):
    state: dict = {}
    respx.route(url__startswith=ENTRY).mock(side_effect=fake_dsm(state))
    p = SynologyProvider(URL, "qr", "right", verify_ssl=False, base_folder="/Kadrlar")
    health = await p.test_connection()
    assert health.ok
    quota = await p.get_quota()
    assert quota.total == 1000 and quota.used == 950
    f = tmp_path / "x.pdf"
    f.write_bytes(b"data")
    await p.ensure_folder("/Kadrlar/ali")
    state["expire"] = True  # sessiya eskirdi — avtomatik qayta login
    remote = await p.upload(f, "/Kadrlar/ali", "Ариза.pdf")
    assert remote.path == "/Kadrlar/ali/Ариза.pdf" and state["uploaded"]
    link = await p.create_public_link(RemoteFile(path=remote.path))
    assert link.url == "https://gofile.me/abc" and link.id == "L1"
    await p.close()


@respx.mock
async def test_wrong_password():
    respx.route(url__startswith=ENTRY).mock(side_effect=fake_dsm({}))
    p = SynologyProvider(URL, "qr", "wrong")
    with pytest.raises(StorageAuthError):
        await p.test_connection()
    await p.close()


@respx.mock
async def test_disk_full(tmp_path: Path):
    respx.route(url__startswith=ENTRY).mock(side_effect=fake_dsm({"full": True}))
    p = SynologyProvider(URL, "qr", "right")
    f = tmp_path / "x"
    f.write_bytes(b"1")
    with pytest.raises(StorageQuota):
        await p.upload(f, "/K", "x")
    await p.close()
