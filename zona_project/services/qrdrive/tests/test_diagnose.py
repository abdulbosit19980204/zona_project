"""Diagnostika: bosqichlar, xato bo'lsa sabab va yechim, sinov fayli o'chiriladi."""
from __future__ import annotations

from qrdrive.db.models import Storage
from qrdrive.storage import registry
from qrdrive.storage.diagnose import diagnose

from .conftest import auth


async def test_diagnose_local_ok(storage_root):
    st = Storage(name="Disk", kind="local", base_folder="/Kadrlar", link_mode="system")
    registry.set_config(st, {"root": str(storage_root)})
    r = await diagnose(st)
    assert r["ok"] and [s["key"] for s in r["steps"]] == ["config", "connect", "folder", "write", "link", "quota"]
    assert st.status == "ok"
    assert not (storage_root / "Kadrlar" / "_qrdrive_tekshiruv").exists()  # sinov papkasi o'chirildi


async def test_diagnose_missing_credentials():
    st = Storage(name="NAS", kind="synology", base_folder="/")
    registry.set_config(st, {"url": "https://nas.local"})
    r = await diagnose(st)
    assert not r["ok"] and r["steps"][0]["error"]["kind"] == "not_configured"
    assert all(s["ok"] is None for s in r["steps"][1:])


async def test_diagnose_endpoint(client, local_storage):
    r = await client.post(f"/qrdrive/api/admin/storages/{local_storage.id}/diagnose", headers=auth("editor"))
    assert r.status_code == 200 and r.json()["ok"] and r.json()["storage"]["status"] == "ok"
    kinds = (await client.get("/qrdrive/api/admin/storages/kinds", headers=auth("viewer"))).json()
    assert all(k["guide"] for k in kinds)
