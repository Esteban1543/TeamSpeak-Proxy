"""Repository: acceso a la tabla `redirects` en SQLite."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import aiosqlite

from app.domain.errors import PortRangeExhausted
from app.domain.models import Redirect, RedirectStatus
from app.infrastructure.db.database import Database

_COLUMNS = (
    "target_raw, target_host, target_port, is_domain, resolved_ip, resolved_port, "
    "port, status, error, created_at, updated_at, resolved_at, alias"
)
_PLACEHOLDERS = ",".join("?" * len(_COLUMNS.split(",")))


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _to_row(r: Redirect) -> tuple:
    return (
        r.target_raw,
        r.target_host,
        r.target_port,
        int(r.is_domain),
        r.resolved_ip,
        r.resolved_port,
        r.port,
        r.status.value,
        r.error,
        _iso(r.created_at),
        _iso(r.updated_at),
        _iso(r.resolved_at),
        r.alias,
    )


def _from_row(row: aiosqlite.Row) -> Redirect:
    return Redirect(
        id=row["id"],
        target_raw=row["target_raw"],
        target_host=row["target_host"],
        target_port=row["target_port"],
        is_domain=bool(row["is_domain"]),
        resolved_ip=row["resolved_ip"],
        resolved_port=row["resolved_port"],
        port=row["port"],
        alias=row["alias"],
        status=RedirectStatus(row["status"]),
        error=row["error"],
        created_at=_dt(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_dt(row["updated_at"]),  # type: ignore[arg-type]
        resolved_at=_dt(row["resolved_at"]),
    )


class SqliteRedirectRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def allocate_and_insert(
        self, build: Callable[[int], Redirect], choose_port: Callable[[set[int]], int]
    ) -> Redirect:
        async with self._db.transaction() as conn:
            async with conn.execute("SELECT port FROM redirects") as cur:
                used = {row[0] for row in await cur.fetchall()}
            port = choose_port(used)  # puede lanzar PortRangeExhausted -> ROLLBACK
            redirect = build(port)
            try:
                cur = await conn.execute(
                    f"INSERT INTO redirects ({_COLUMNS}) VALUES ({_PLACEHOLDERS})",
                    _to_row(redirect),
                )
            except aiosqlite.IntegrityError as exc:  # UNIQUE(port): no debería ocurrir
                raise PortRangeExhausted(f"El puerto {port} ya está en uso") from exc
            redirect.id = cur.lastrowid
            return redirect

    async def list(self) -> list[Redirect]:
        async with self._db.conn.execute("SELECT * FROM redirects ORDER BY id") as cur:
            return [_from_row(row) for row in await cur.fetchall()]

    async def get(self, redirect_id: int) -> Redirect | None:
        async with self._db.conn.execute("SELECT * FROM redirects WHERE id = ?", (redirect_id,)) as cur:
            row = await cur.fetchone()
        return _from_row(row) if row else None

    async def update(self, redirect: Redirect) -> None:
        sets = ", ".join(f"{c.strip()} = ?" for c in _COLUMNS.split(","))
        async with self._db.transaction() as conn:
            await conn.execute(f"UPDATE redirects SET {sets} WHERE id = ?", (*_to_row(redirect), redirect.id))

    async def delete(self, redirect_id: int) -> bool:
        async with self._db.transaction() as conn:
            cur = await conn.execute("DELETE FROM redirects WHERE id = ?", (redirect_id,))
            return cur.rowcount > 0

    async def used_ports(self) -> set[int]:
        async with self._db.conn.execute("SELECT port FROM redirects") as cur:
            return {row[0] for row in await cur.fetchall()}
