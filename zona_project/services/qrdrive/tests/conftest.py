from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="qrdrive-test-"))
os.environ.update(QRDRIVE_DATA_DIR=str(_TMP / "data"), QRDRIVE_DB_PATH=str(_TMP / "data" / "test.sqlite3"),
                  QRDRIVE_MASTER_KEY="test-master", QRDRIVE_SSO_SECRET="test-sso-secret-0123456789abcdef-xyz", QRDRIVE_DEBUG="1",
                  QRDRIVE_PUBLIC_BASE_URL="http://testserver", QRDRIVE_SEED_DEFAULT="0")

import httpx  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402

from qrdrive import settings_store  # noqa: E402
from qrdrive.core.config import config  # noqa: E402
from qrdrive.db import session as dbsession  # noqa: E402
from qrdrive.db.models import Employee, Storage  # noqa: E402
from qrdrive.main import app  # noqa: E402
from qrdrive.services import system  # noqa: E402
from qrdrive.storage import registry  # noqa: E402


@pytest.fixture(autouse=True)
async def fresh_db():
    await dbsession.dispose()
    for p in (config.db_path, config.db_path + "-wal", config.db_path + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    settings_store.invalidate()
    await system.bootstrap()
    yield
    await dbsession.dispose()


@pytest.fixture
async def session():
    async with dbsession.session_scope() as s:
        yield s


def sso_token(role: str = "admin", username: str = "ali", exp: int = 600, token_type: str = "access") -> str:
    return jwt.encode({"token_type": token_type, "exp": int(time.time()) + exp, "user_id": 1, "username": username,
                       "name": "Ali Valiyev", "zrole": role}, "test-sso-secret-0123456789abcdef-xyz", algorithm="HS256")


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def auth(role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {sso_token(role)}"}


@pytest.fixture
def storage_root():
    root = _TMP / f"files-{time.time_ns()}"
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
async def local_storage(session, storage_root) -> Storage:
    st = Storage(name="Disk", kind="local", base_folder="/Kadrlar", is_primary=True, link_mode="system", status="ok")
    registry.set_config(st, {"root": str(storage_root)})
    session.add(st)
    await session.commit()
    return st


@pytest.fixture
async def employee(session) -> Employee:
    emp = Employee(full_name="Olimova Dilnoza", department="Kadrlar", folder="dilnoza")
    session.add(emp)
    await session.commit()
    return emp
