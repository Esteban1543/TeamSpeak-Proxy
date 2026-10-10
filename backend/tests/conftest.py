from __future__ import annotations

import bcrypt
import pytest

from app.config import Settings
from app.domain.errors import ResolveError

PASSWORD = "supersecreta123"
PASSWORD_HASH = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        api_host="127.0.0.1",
        api_port=8000,
        database_path=str(tmp_path / "proxy.db"),
        port_range_start=41000,
        port_range_end=41002,
        public_host="203.0.113.10",
        admin_user="admin",
        admin_password_hash=PASSWORD_HASH,
        session_secret="x" * 40,
        session_cookie_secure=False,
        _env_file=None,
    )
    values.update(overrides)
    return Settings(**values)


class FakeResolver:
    """Resolver en memoria: dominio -> (ip, puerto)."""

    def __init__(self, table: dict[str, tuple[str, int]] | None = None) -> None:
        self.table = table or {}

    async def resolve(self, host: str, port: int | None) -> tuple[str, int]:
        if host[0].isdigit() or ":" in host:
            return host, port or 9987
        if host not in self.table:
            raise ResolveError(f"No se encontró {host}")
        ip, srv_port = self.table[host]
        return ip, port or srv_port


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path)
