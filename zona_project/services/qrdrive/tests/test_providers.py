"""Yangi provayderlar: WebDAV/Nextcloud (respx), S3 (moto), Google Drive (respx), Synology Drive papka ID'si."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from qrdrive.core.errors import NotSupported, StorageAuthError
from qrdrive.storage.base import RemoteFile
from qrdrive.storage.gdrive import GoogleDriveProvider
from qrdrive.storage.synology import SynologyProvider, drive_to_filestation, parse_drive_folder
from qrdrive.storage.webdav import WebDAVProvider

DAV = "https://cloud.test/remote.php/dav/files/qr"


def test_parse_drive_folder():
    assert parse_drive_folder("https://file.stargroup.uz/#file_id=984701843502314054") == "984701843502314054"
    assert parse_drive_folder("984701843502314054") == "984701843502314054"
    assert parse_drive_folder("") is None
    assert drive_to_filestation("/team-folders/Kadrlar/QR") == "/Kadrlar/QR"
    assert drive_to_filestation("/mydrive/QR") == "/home/QR"


@respx.mock
async def test_synology_drive_resolve():
    def handler(request: httpx.Request) -> httpx.Response:
        p = dict(request.url.params)
        if request.method == "POST":
            p.update(dict(httpx.QueryParams(request.content.decode())))
        if p.get("api") == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "S"}})
        if p.get("api") == "SYNO.SynologyDrive.Files":
            assert p["path"] == "id:984701843502314054"
            return httpx.Response(200, json={"success": True, "data": {"display_path": "/team-folders/Kadrlar/QR Drive"}})
        return httpx.Response(200, json={"success": True, "data": {}})

    respx.route(url__startswith="https://file.stargroup.uz/webapi/").mock(side_effect=handler)
    p = SynologyProvider("https://file.stargroup.uz", "u", "p")
    assert await p.resolve_drive_folder("984701843502314054") == "/Kadrlar/QR Drive"
    await p.close()


PROPFIND_LIST = f"""<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">
<d:response><d:href>/remote.php/dav/files/qr/Kadrlar/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/remote.php/dav/files/qr/Kadrlar/ali/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/remote.php/dav/files/qr/Kadrlar/%D0%90%D1%80%D0%B8%D0%B7%D0%B0.pdf</d:href><d:propstat><d:prop><d:resourcetype/>
<d:getcontentlength>42</d:getcontentlength><d:getlastmodified>Mon, 16 Nov 2026 10:00:00 GMT</d:getlastmodified></d:prop></d:propstat></d:response>
</d:multistatus>"""


@respx.mock
async def test_webdav_nextcloud(tmp_path: Path):
    respx.request("PROPFIND", f"{DAV}/").mock(return_value=httpx.Response(207, text="""<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">
<d:response><d:href>/remote.php/dav/files/qr/</d:href><d:propstat><d:prop><d:quota-used-bytes>100</d:quota-used-bytes>
<d:quota-available-bytes>900</d:quota-available-bytes></d:prop></d:propstat></d:response></d:multistatus>"""))
    mk = respx.request("MKCOL", url__startswith=DAV).mock(side_effect=[httpx.Response(405), httpx.Response(201)])
    put = respx.put(url__startswith=DAV).mock(return_value=httpx.Response(201))
    share = respx.post("https://cloud.test/ocs/v2.php/apps/files_sharing/api/v1/shares").mock(
        return_value=httpx.Response(200, json={"ocs": {"data": {"id": 77, "url": "https://cloud.test/s/AbC"}}}))
    respx.request("PROPFIND", f"{DAV}/Kadrlar").mock(return_value=httpx.Response(207, text=PROPFIND_LIST))
    p = WebDAVProvider(DAV, "qr", "app-pass")
    assert (await p.test_connection()).ok
    q = await p.get_quota()
    assert q.used == 100 and q.total == 1000
    f = tmp_path / "a.pdf"
    f.write_bytes(b"x" * 42)
    await p.ensure_folder("/Kadrlar/ali")
    assert mk.call_count == 2
    remote = await p.upload(f, "/Kadrlar/ali", "Ариза.pdf")
    assert remote.path == "/Kadrlar/ali/Ариза.pdf" and put.calls.last.request.url.raw_path.endswith(b"/Kadrlar/ali/%D0%90%D1%80%D0%B8%D0%B7%D0%B0.pdf")
    link = await p.create_public_link(remote, datetime.now(timezone.utc) + timedelta(days=3), "sir")
    assert link.url == "https://cloud.test/s/AbC" and link.id == "77"
    body = share.calls.last.request.content.decode()
    assert "shareType=3" in body and "password=sir" in body and "expireDate=" in body
    entries = await p.list("/Kadrlar")
    assert [(e.name, e.is_dir, e.size) for e in entries] == [("ali", True, None), ("Ариза.pdf", False, 42)]
    await p.close()


@respx.mock
async def test_webdav_wrong_password():
    respx.request("PROPFIND", f"{DAV}/").mock(return_value=httpx.Response(401))
    p = WebDAVProvider(DAV, "qr", "bad", nextcloud=False)
    with pytest.raises(StorageAuthError):
        await p.test_connection()
    with pytest.raises(NotSupported):
        await p.create_public_link(RemoteFile(path="/a"))
    await p.close()


def test_s3_with_moto(tmp_path: Path):
    import asyncio

    from moto import mock_aws

    from qrdrive.storage.s3 import S3Provider

    async def scenario():
        p = S3Provider("qr-bucket", "AKIA", "secret", region="us-east-1")
        p.client.create_bucket(Bucket="qr-bucket")
        assert (await p.test_connection()).ok
        f = tmp_path / "x.txt"
        f.write_bytes(b"s3 data")
        remote = await p.upload(f, "/Kadrlar/ali", "x.txt")
        assert remote.path == "/Kadrlar/ali/x.txt"
        link = await p.create_public_link(remote, datetime.now(timezone.utc) + timedelta(days=2))
        assert "X-Amz-Signature" in link.url and "Kadrlar/ali/x.txt" in link.url
        with pytest.raises(NotSupported):  # muddatsiz -> tizim havolasi
            await p.create_public_link(remote, None)
        with pytest.raises(NotSupported):  # 7 kundan ortiq
            await p.create_public_link(remote, datetime.now(timezone.utc) + timedelta(days=30))
        entries = await p.list("/Kadrlar")
        assert [(e.name, e.is_dir) for e in entries] == [("ali", True)]
        data = b"".join([c async for c in p.open_stream(remote.path)])
        assert data == b"s3 data"
        new = await p.rename(remote.path, "y.txt")
        assert new == "/Kadrlar/ali/y.txt"
        await p.delete(new)
        assert await p.list("/Kadrlar/ali") == []

    with mock_aws():
        asyncio.run(scenario())


def _service_account() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return json.dumps({"type": "service_account", "client_email": "qr@proj.iam.gserviceaccount.com", "private_key": pem})


@respx.mock
async def test_google_drive_service_account(tmp_path: Path):
    token = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "AT", "expires_in": 3600}))
    respx.get("https://www.googleapis.com/drive/v3/files/SD1").mock(return_value=httpx.Response(200, json={"id": "SD1"}))
    created = []

    def files_list(request: httpx.Request) -> httpx.Response:
        q = request.url.params["q"]
        assert request.url.params["driveId"] == "SD1" and request.url.params["supportsAllDrives"] == "true"
        if "name = 'Kadrlar'" in q:
            return httpx.Response(200, json={"files": [{"id": "F1", "name": "Kadrlar", "mimeType": "application/vnd.google-apps.folder"}]})
        return httpx.Response(200, json={"files": []})

    respx.get("https://www.googleapis.com/drive/v3/files").mock(side_effect=files_list)

    def create_folder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        created.append((body["name"], body["parents"]))
        return httpx.Response(200, json={"id": "F2"})

    respx.post("https://www.googleapis.com/drive/v3/files").mock(side_effect=create_folder)
    respx.post("https://www.googleapis.com/upload/drive/v3/files").mock(
        return_value=httpx.Response(200, headers={"location": "https://upload.test/session1"}))
    respx.put("https://upload.test/session1").mock(return_value=httpx.Response(200, json={"id": "FILE9"}))
    respx.post("https://www.googleapis.com/drive/v3/files/FILE9/permissions").mock(return_value=httpx.Response(200, json={"id": "anyoneWithLink"}))
    respx.get("https://www.googleapis.com/drive/v3/files/FILE9").mock(
        return_value=httpx.Response(200, json={"webViewLink": "https://drive.google.com/file/d/FILE9/view"}))

    p = GoogleDriveProvider({"auth": "service_account", "service_account_json": _service_account(), "shared_drive_id": "SD1"})
    assert (await p.test_connection()).ok
    f = tmp_path / "a.pdf"
    f.write_bytes(b"pdf")
    remote = await p.upload(f, "/Kadrlar/ali", "a.pdf")
    assert remote.id == "FILE9" and created == [("ali", ["F1"])]
    link = await p.create_public_link(remote)
    assert link.url.endswith("/FILE9/view") and link.id == "FILE9:anyoneWithLink"
    with pytest.raises(NotSupported):
        await p.create_public_link(remote, password="x")
    assert token.call_count == 1  # token keshlanadi
    await p.close()


async def test_google_drive_needs_shared_drive():
    p = GoogleDriveProvider({"auth": "service_account", "service_account_json": _service_account()})
    from qrdrive.core.errors import StoragePermission
    with pytest.raises(StoragePermission):
        await p.test_connection()
    p2 = GoogleDriveProvider({"auth": "oauth", "client_id": "c"})
    with pytest.raises(StorageAuthError):
        await p2.test_connection()
    await p.close()
    await p2.close()
