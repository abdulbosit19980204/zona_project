"""Fayl yangilanishi (QR o'zgarmaydi), arxivni papka qilish (bitta QR), xavfsiz ochish, oldindan yuklab olish, sessiya keshi."""
from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select

from qrdrive import settings_store
from qrdrive.core.errors import FileTooBig
from qrdrive.db.models import FileRecord, TgAccount
from qrdrive.db.session import session_scope
from qrdrive.services import pipeline
from qrdrive.services.archive import ArchiveError, extract, is_archive
from qrdrive.services.files import enqueue, spool_path
from qrdrive.storage import registry

from .conftest import auth
from .test_pipeline import run


def make_zip(files: dict[str, bytes], cp866: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        for i, (name, data) in enumerate((cp866 or {}).items()):  # joy egallovchi — keyin cp866 baytlari bilan almashtiriladi
            zf.writestr(f"~{i}~".ljust(len(name.encode("cp866")), "_"), data)
    raw = buf.getvalue()
    for i, name in enumerate((cp866 or {})):  # Windows arxivlovchisi: UTF-8 bayrog'isiz, cp866 kodlangan nom
        raw = raw.replace(f"~{i}~".ljust(len(name.encode("cp866")), "_").encode(), name.encode("cp866"))
    return raw


def test_extract_safety(tmp_path: Path):
    z = tmp_path / "a.zip"
    z.write_bytes(make_zip({"docs/a.pdf": b"A", "../../evil.txt": b"x", "__MACOSX/._a": b"m", "b.txt": b"BB"},
                           cp866={"Ариза.docx": b"CYR"}))
    ex = extract(z, tmp_path / "out", max_files=100, max_bytes=10_000)
    names = [n for n, _ in ex.files]
    assert names == ["b.txt", "docs/a.pdf", "Ариза.docx"]  # ../ li fayl va __MACOSX tashlab yuborildi
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path / "out" / "evil.txt").exists() and ex.skipped == 2
    assert (tmp_path / "out" / "Ариза.docx").read_bytes() == b"CYR"
    with pytest.raises(FileTooBig):
        extract(z, tmp_path / "o2", max_files=100, max_bytes=3)
    with pytest.raises(ArchiveError):
        extract(z, tmp_path / "o3", max_files=2, max_bytes=10_000)
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ArchiveError):
        extract(bad, tmp_path / "o4", max_files=10, max_bytes=100)


def test_extract_tar_skips_symlinks(tmp_path: Path):
    t = tmp_path / "a.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        data = b"hello"
        info = tarfile.TarInfo("dir/x.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("dir/link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tf.addfile(link)
    ex = extract(t, tmp_path / "o", max_files=10, max_bytes=100)
    assert ex.files == [("dir/x.txt", 5)]
    assert is_archive("A.TAR.GZ") and is_archive("x.zip") and not is_archive("x.pdf")


async def upload(client, employee, name: str, data: bytes, **form) -> int:
    r = await client.post("/qrdrive/api/admin/files/upload", headers=auth("admin"),
                          data={"employee_id": str(employee.id), **{k: str(v).lower() for k, v in form.items()}},
                          files={"files": (name, data, "application/octet-stream")})
    fid = r.json()[0]["id"]
    await run(fid)
    return fid


async def test_archive_as_folder_one_qr(client, local_storage, employee, storage_root):
    data = make_zip({"Buyruqlar/1.pdf": b"one", "2.xlsx": b"two"}, cp866={"Ариза.txt": b"three"})
    fid = await upload(client, employee, "Hujjatlar.zip", data, extract=True)
    f = (await client.get(f"/qrdrive/api/admin/files/{fid}", headers=auth())).json()
    assert f["status"] == "delivered" and f["kind"] == "folder" and len(f["items"]) == 3
    assert f["remote_path"].startswith("/Kadrlar/dilnoza/Hujjatlar_")
    folder = storage_root / f["remote_path"].lstrip("/")
    assert (folder / "Buyruqlar" / "1.pdf").read_bytes() == b"one" and (folder / "Ариза.txt").read_bytes() == b"three"
    page = await client.get(f["url"].replace("http://testserver", ""))
    assert page.status_code == 200 and "3 ta fayl" in page.text and "Buyruqlar/1.pdf" in page.text
    idx = [i["name"] for i in f["items"]].index("2.xlsx")
    item = await client.get(f["url"].replace("http://testserver", "") + f"/{idx}")
    assert item.content == b"two"
    assert (await client.get(f"/qrdrive/api/admin/files/{fid}/items/{idx}", headers=auth())).content == b"two"
    # parolli papka: ro'yxatdan keyin cookie bilan fayllar ochiladi
    r = await client.post(f"/qrdrive/api/admin/files/{fid}/link", headers=auth("admin"), json={"password": "777"})
    url = r.json()["url"].replace("http://testserver", "")
    assert "parol" in (await client.get(url + "/0")).text.lower()
    async with httpx.AsyncClient(transport=client._transport, base_url="http://testserver") as c2:
        listing = await c2.post(url, data={"password": "777"})
        assert "3 ta fayl" in listing.text
        assert (await c2.get(url + f"/{idx}")).content == b"two"


async def test_archive_kept_as_archive_by_default(client, local_storage, employee):
    fid = await upload(client, employee, "a.zip", make_zip({"x.txt": b"x"}))
    f = (await client.get(f"/qrdrive/api/admin/files/{fid}", headers=auth())).json()
    assert f["kind"] == "file" and f["remote_path"].endswith(".zip")


async def test_replace_keeps_link_and_versions(client, local_storage, employee, storage_root):
    v1 = await upload(client, employee, "x.xlsx", b"VERSION-1")
    f1 = (await client.get(f"/qrdrive/api/admin/files/{v1}", headers=auth())).json()
    v2 = await upload(client, employee, "x.xlsx", b"VERSION-2", replace=True)
    f2 = (await client.get(f"/qrdrive/api/admin/files/{v2}", headers=auth())).json()
    assert f2["url"] == f1["url"] and f2["remote_path"] == f1["remote_path"] and f2["version"] == 2
    assert (storage_root / f1["remote_path"].lstrip("/")).read_bytes() == b"VERSION-2"
    assert (await client.get(f1["url"].replace("http://testserver", ""))).content == b"VERSION-2"  # eski QR — yangi tarkib
    assert [v["version"] for v in f2["versions"]] == [2, 1]
    listed = (await client.get("/qrdrive/api/admin/files", headers=auth())).json()["items"]
    assert [i["id"] for i in listed] == [v2]  # ro'yxatda faqat joriy versiya
    # tarkib o'zgarmagan bo'lsa — yangi versiya emas
    v3 = await upload(client, employee, "x.xlsx", b"VERSION-2", replace=True)
    f3 = (await client.get(f"/qrdrive/api/admin/files/{v3}", headers=auth())).json()
    assert f3["url"] == f1["url"] and f3["duplicate_of"] == v2
    # eski versiyani butunlay o'chirish joriy faylni o'chirmaydi
    await client.delete(f"/qrdrive/api/admin/files/{v1}", headers=auth("admin"))
    assert (await client.delete(f"/qrdrive/api/admin/files/{v1}/purge", headers=auth("admin"))).status_code == 200
    assert (storage_root / f1["remote_path"].lstrip("/")).read_bytes() == b"VERSION-2"
    assert (await client.get(f1["url"].replace("http://testserver", ""))).content == b"VERSION-2"


async def test_new_file_when_not_replacing(client, local_storage, employee):
    a = await upload(client, employee, "x.xlsx", b"A")
    b = await upload(client, employee, "x.xlsx", b"B")
    fa = (await client.get(f"/qrdrive/api/admin/files/{a}", headers=auth())).json()
    fb = (await client.get(f"/qrdrive/api/admin/files/{b}", headers=auth())).json()
    assert fa["url"] != fb["url"] and fa["remote_path"] != fb["remote_path"]


async def test_bot_plan_and_choice(session, employee, local_storage):
    from qrdrive.bot.main import plan_choices
    acc = TgAccount(telegram_id=4242, employee_id=employee.id, status="active")
    session.add(acc)
    await session.commit()
    s = await settings_store.load(session, fresh=True)
    plan = await plan_choices(session, acc, s, "Hujjatlar.zip")
    assert [[a for _, a, _ in row] for row in plan["rows"]] == [["archive", "archive"], ["folder", "folder"]]
    path = spool_path("t")
    path.write_bytes(b"v1")
    prev = await enqueue(session, source="web", original_name="x.xlsx", employee_id=employee.id, temp_path=path, size=2)
    await session.commit()
    await run(prev.id)
    async with session_scope() as s2:
        plan = await plan_choices(s2, acc, s, "x.xlsx")
    assert plan["rows"][0][0][1] == f"replace{prev.id}" and [v for _, _, v in plan["rows"][1]] == ["public", "private"]
    assert "avval yuklangan" in plan["text"]
    await settings_store.save(session, {"replace_mode": "replace", "visibility_mode": "public"})
    async with session_scope() as s2:
        plan = await plan_choices(s2, acc, await settings_store.load(s2, fresh=True), "x.xlsx")
    assert plan["rows"] == [] and plan["options"] == {"visibility": "public", "replace_of": prev.id}


@respx.mock
async def test_prefetch_while_waiting(session, employee):
    await settings_store.save(session, {"bot_token": "123456:" + "C" * 35})
    base = "https://api.telegram.org/bot123456:" + "C" * 35
    respx.post(f"{base}/getFile").mock(return_value=httpx.Response(200, json={"ok": True, "result": {"file_path": "d/f.pdf"}}))
    respx.get("https://api.telegram.org/file/bot123456:" + "C" * 35 + "/d/f.pdf").mock(return_value=httpx.Response(200, content=b"PRE"))
    rec = await enqueue(session, source="telegram", original_name="f.pdf", employee_id=employee.id,
                        tg={"chat_id": 1, "file_id": "FID", "status_msg_id": 2}, awaiting=True)
    await session.commit()
    async with session_scope() as s:
        fid = await pipeline.claim_prefetch(s)
    assert fid == rec.id
    async with session_scope() as s:
        await pipeline.prefetch(s, fid)
    async with session_scope() as s:
        r = await s.get(FileRecord, rec.id)
        assert r.status == "awaiting" and Path(r.temp_path).read_bytes() == b"PRE" and r.locked_until is None
        assert await pipeline.claim_prefetch(s) is None  # qayta yuklab olinmaydi


async def test_provider_cache(local_storage, monkeypatch):
    monkeypatch.setattr(registry, "CACHE_ENABLED", True)
    registry._CACHE.clear()
    async with registry.use(local_storage) as a:
        pass
    async with registry.use(local_storage) as b:
        pass
    assert a is b
    local_storage.base_folder = "/Boshqa"  # sozlama o'zgarsa — yangi provayder
    async with registry.use(local_storage) as c:
        pass
    assert c is not a
    registry._CACHE.clear()


async def test_move_updates_all_versions(client, local_storage, employee, storage_root):
    v1 = await upload(client, employee, "m.xlsx", b"1")
    v2 = await upload(client, employee, "m.xlsx", b"2", replace=True)
    r = await client.post(f"/qrdrive/api/admin/files/{v2}/move", headers=auth("admin"), json={"folder": "/Kadrlar/Arxiv/2026"})
    assert r.status_code == 200, r.text
    new_path = r.json()["remote_path"]
    assert new_path.startswith("/Kadrlar/Arxiv/2026/") and (storage_root / new_path.lstrip("/")).read_bytes() == b"2"
    old = (await client.get(f"/qrdrive/api/admin/files/{v1}", headers=auth())).json()
    assert old["remote_path"] == new_path
    browse = (await client.get("/qrdrive/api/admin/files/browse", headers=auth(), params={"storage_id": local_storage.id, "path": "/Kadrlar"})).json()
    assert "Arxiv" in [e["name"] for e in browse["entries"] if e["is_dir"]]  # papka tanlagich shu ro'yxatni ko'rsatadi
