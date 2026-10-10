"""Conexión SQLite (aiosqlite) y esquema."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS redirects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_raw    TEXT    NOT NULL,
    target_host   TEXT    NOT NULL,
    target_port   INTEGER,
    is_domain     INTEGER NOT NULL,
    resolved_ip   TEXT    NOT NULL,
    resolved_port INTEGER NOT NULL,
    port          INTEGER NOT NULL UNIQUE,
    status        TEXT    NOT NULL,
    error         TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    resolved_at   TEXT
);
"""


class Database:
    """Una única conexión compartida; las escrituras se serializan con un lock
    además de la transacción `BEGIN IMMEDIATE` de SQLite."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: control manual de transacciones.
        self._conn = await aiosqlite.connect(self._path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(SCHEMA)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Base de datos no conectada")
        return self._conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._write_lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            else:
                await self.conn.execute("COMMIT")
