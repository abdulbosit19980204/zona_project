"""Pipeline: muvaffaqiyat, takroriy fayl, qayta urinish, hajm cheklovi, zaxira saqlash joyi."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from qrdrive import settings_store
from qrdrive.db.models import FileEvent, FileRecord, Notification, Storage, SystemLink
from qrdrive.db.session import session_scope
from qrdrive.services import pipeline
from qrdrive.services.files import enqueue, spool_path
from qrdrive.storage import registry
from qrdrive.storage.local import LocalProvider


def make_temp(content: bytes = b"hello world") -> tuple:
    p = spool_path("t")
    p.write_bytes(content)
    return p, len(content)


async def run(file_id: int) -> FileRecord:
    async with session_scope() as s:
        await pipeline.process(s, file_id)
    async with session_scope() as s:
        return await s.get(FileRecord, file_id)


async def new_file(session, employee=None, content=b"hello world", name="Ariza №1 — Ўзбек.pdf") -> int:
    path, size = make_temp(content)
    rec = await enqueue(session, source="web", original_name=name, employee_id=employee.id if employee else None,
                        temp_path=path, size=size)
    await session.commit()
    return rec.id


async def test_success_creates_file_and_system_link(session, local_storage, employee, storage_root):
    fid = await new_file(session, employee)
    rec = await run(fid)
    assert rec.status == "delivered", rec.error_text
    assert rec.link_kind == "system" and rec.link_url.startswith("http://testserver/qrdrive/s/")
    assert rec.remote_path.startswith("/Kadrlar/dilnoza/")
    assert "Ариза" not in rec.stored_name and "Ўзбек" in rec.stored_name  # kirill harflari saqlanadi
    stored = storage_root / rec.remote_path.lstrip("/")
    assert stored.read_bytes() == b"hello world"
    assert not rec.temp_path
    async with session_scope() as s:
        stages = [e.stage for e in (await s.execute(select(FileEvent).where(FileEvent.file_id == fid))).scalars()]
        assert stages == ["received", "downloading", "uploading", "sharing", "qr_generated", "delivered"]
        assert await s.get(SystemLink, rec.link_id)


async def test_duplicate_reuses_previous_link(session, local_storage, employee, storage_root):
    first = await run(await new_file(session, employee))
    second = await run(await new_file(session, employee))
    assert second.status == "delivered" and second.duplicate_of == first.id
    assert second.link_url == first.link_url
    assert len(list((storage_root / "Kadrlar" / "dilnoza").iterdir())) == 1


async def test_duplicate_policy_upload(session, local_storage, employee):
    await settings_store.save(session, {"duplicate_policy": "upload"})
    first = await run(await new_file(session, employee))
    second = await run(await new_file(session, employee))
    assert second.duplicate_of is None and second.link_url != first.link_url


async def test_retry_then_fail_then_manual_retry(session, local_storage, employee, monkeypatch):
    calls = {"n": 0}
    real_upload = LocalProvider.upload

    async def broken(self, *a, **kw):
        calls["n"] += 1
        raise httpx.ConnectError("NAS o'chiq")

    monkeypatch.setattr(LocalProvider, "upload", broken)
    fid = await new_file(session, employee)
    rec = await run(fid)
    assert rec.status == "retrying" and rec.attempts == 1 and rec.error_kind == "storage_down"
    assert (rec.next_attempt_at - datetime.now(timezone.utc)).total_seconds() > 5
    for _ in range(3):
        rec = await run(fid)
    assert rec.status == "failed" and rec.attempts == 4 and calls["n"] == 4
    assert rec.temp_path  # vebdan yuklangan fayl qayta urinish uchun saqlanadi
    async with session_scope() as s:
        n = (await s.execute(select(func.count()).select_from(Notification).where(Notification.kind == "file_failed"))).scalar_one()
        assert n == 1
    # saqlash joyi tiklandi — «Qayta urinish»
    monkeypatch.setattr(LocalProvider, "upload", real_upload)
    async with session_scope() as s:
        r = await s.get(FileRecord, fid)
        await pipeline.retry(s, r)
        await s.commit()
    async with session_scope() as s:
        assert await pipeline.claim_next(s) == fid
    rec = await run(fid)
    assert rec.status == "delivered"


async def test_too_big_fails_without_retry(session, local_storage, employee):
    await settings_store.save(session, {"max_file_mb": 1})
    rec = await run(await new_file(session, employee, content=b"x" * (1024 * 1024 + 10)))
    assert rec.status == "failed" and rec.error_kind == "too_big" and rec.attempts == 1


async def test_type_not_allowed(session, local_storage, employee):
    await settings_store.save(session, {"allowed_types": "pdf, docx"})
    rec = await run(await new_file(session, employee, name="virus.exe"))
    assert rec.status == "failed" and rec.error_kind == "type_not_allowed"


async def test_no_storage(session, employee):
    rec = await run(await new_file(session, employee))
    assert rec.status == "failed" and rec.error_kind == "no_storage"


async def test_fallback_storage(session, local_storage, employee, storage_root, monkeypatch):
    backup = Storage(name="Zaxira", kind="local", base_folder="/Zaxira", is_fallback=True, link_mode="system", status="ok")
    registry.set_config(backup, {"root": str(storage_root / "fb")})
    session.add(backup)
    await settings_store.save(session, {"auto_fallback": True})
    real = LocalProvider.upload

    async def flaky(self, local_path, dest_folder, filename):
        if dest_folder.startswith("/Kadrlar"):
            raise httpx.ConnectTimeout("timeout")
        return await real(self, local_path, dest_folder, filename)

    monkeypatch.setattr(LocalProvider, "upload", flaky)
    rec = await run(await new_file(session, employee))
    assert rec.status == "delivered" and rec.storage_id == backup.id and rec.remote_path.startswith("/Zaxira/")


async def test_switch_primary_without_restart(session, local_storage, employee, storage_root):
    """Qabul mezoni 3: asosiy saqlash joyi almashsa, keyingi fayllar yangisiga tushadi."""
    other = Storage(name="Yangi", kind="local", base_folder="/Yangi", link_mode="system", status="ok")
    registry.set_config(other, {"root": str(storage_root / "new")})
    session.add(other)
    local_storage.is_primary = False
    other.is_primary = True
    await session.commit()
    rec = await run(await new_file(session, employee))
    assert rec.storage_id == other.id


async def test_folder_from_username_when_empty(session, local_storage):
    from qrdrive.db.models import Employee, TgAccount
    emp = Employee(full_name="Xodim 1")
    session.add(emp)
    await session.flush()
    acc = TgAccount(telegram_id=777, username="kadr_ali", employee_id=emp.id, status="active")
    session.add(acc)
    await session.commit()
    path, size = make_temp()
    rec = await enqueue(session, source="web", original_name="a.txt", employee_id=emp.id, account_id=acc.id,
                        temp_path=path, size=size)
    await session.commit()
    rec = await run(rec.id)
    assert "/Kadrlar/kadr_ali/" in rec.remote_path
    async with session_scope() as s:
        assert (await s.get(Employee, emp.id)).folder == "kadr_ali"


async def test_telegram_file_end_to_end(session, local_storage, employee, storage_root):
    """Qabul mezoni 1: botga yuborilgan fayl saqlanadi va xodimga QR yuboriladi."""
    import respx

    await settings_store.save(session, {"bot_token": "123456:" + "B" * 35})
    rec = await enqueue(session, source="telegram", original_name="Ma'lumotnoma.pdf", employee_id=employee.id,
                        tg={"chat_id": 42, "file_id": "FID", "status_msg_id": 7})
    await session.commit()
    base = "https://api.telegram.org/bot123456:" + "B" * 35
    with respx.mock() as mock:
        mock.post(f"{base}/getFile").mock(return_value=httpx.Response(200, json={"ok": True, "result": {"file_path": "documents/f.pdf"}}))
        mock.get("https://api.telegram.org/file/bot123456:" + "B" * 35 + "/documents/f.pdf").mock(
            return_value=httpx.Response(200, content=b"PDF-DATA"))
        edits = mock.post(f"{base}/editMessageText").mock(return_value=httpx.Response(200, json={"ok": True, "result": True}))
        photo = mock.post(f"{base}/sendPhoto").mock(return_value=httpx.Response(200, json={"ok": True, "result": {}}))
        delete = mock.post(f"{base}/deleteMessage").mock(return_value=httpx.Response(200, json={"ok": True, "result": True}))
        done = await run(rec.id)
    assert done.status == "delivered", done.error_text
    assert (storage_root / done.remote_path.lstrip("/")).read_bytes() == b"PDF-DATA"
    assert edits.call_count >= 2 and photo.called and delete.called
    body = photo.calls.last.request.content
    assert b"\x89PNG" in body and done.link_url.encode() in body
