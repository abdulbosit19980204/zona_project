"""SQLite (WAL) ulanishi. API, worker va bot — alohida jarayonlar, bitta servis bazasini bo'lishadi."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..core.config import config
from .models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _on_connect(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=20000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        config.ensure_dirs()
        _engine = create_async_engine(f"sqlite+aiosqlite:///{config.db_path}", connect_args={"timeout": 20})
        event.listen(_engine.sync_engine, "connect", _on_connect)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as s:
        yield s


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as s:
        yield s


def _add_missing_columns(conn) -> None:
    """Yengil migratsiya: yangi ustunlar mavjud jadvalga qo'shiladi (yangi jadvallar — create_all)."""
    insp = inspect(conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = col.type.compile(dialect=conn.dialect)
            default = ""
            if col.default is not None and getattr(col.default, "is_scalar", False):
                val = col.default.arg
                default = f" DEFAULT {int(val) if isinstance(val, bool) else repr(val)}"
            conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}{default}'))


async def init_db() -> None:
    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = _sessionmaker = None
