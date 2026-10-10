"""Configuración de la aplicación, leída de variables de entorno / backend/.env."""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    database_path: str = "/data/proxy.db"

    port_range_start: int = Field(default=10000, ge=1, le=65535)
    port_range_end: int = Field(default=10100, ge=1, le=65535)
    public_host: str = Field(min_length=1)

    admin_user: str = Field(default="admin", min_length=1)
    admin_password_hash: str
    session_secret: str
    session_expire_hours: int = Field(default=12, ge=1)
    session_cookie_secure: bool = True

    dns_refresh_minutes: int = Field(default=10, ge=1)
    forwarding_engine: Literal["asyncio", "nftables"] = "asyncio"

    # Tiempo tras el cual se cierra la sesión UDP de un cliente sin tráfico.
    client_idle_timeout: int = Field(default=120, ge=10)

    @field_validator("admin_password_hash")
    @classmethod
    def _check_hash(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("está vacío; genera uno con: python -m app.hash_password")
        if not v.startswith("$2"):
            raise ValueError("no parece un hash bcrypt (debe empezar por $2b$); usa python -m app.hash_password")
        return v

    @field_validator("session_secret")
    @classmethod
    def _check_secret(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 32:
            raise ValueError("debe tener al menos 32 caracteres; genera uno con: python -m app.hash_password")
        return v

    @model_validator(mode="after")
    def _check_range(self) -> "Settings":
        if self.port_range_end <= self.port_range_start:
            raise ValueError(
                f"PORT_RANGE_END ({self.port_range_end}) debe ser mayor que "
                f"PORT_RANGE_START ({self.port_range_start})"
            )
        if self.port_range_start <= self.api_port <= self.port_range_end:
            raise ValueError(f"API_PORT ({self.api_port}) no puede estar dentro del rango de puertos de proxy")
        return self

    @property
    def port_range(self) -> range:
        return range(self.port_range_start, self.port_range_end + 1)

    @property
    def port_capacity(self) -> int:
        return len(self.port_range)


def _format_error(exc: ValidationError) -> str:
    lines = ["Configuración inválida en backend/.env:"]
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]).upper() or "(general)"
        msg = err["msg"].removeprefix("Value error, ")
        lines.append(f"  - {field}: {msg}")
    return "\n".join(lines)


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        print(_format_error(exc), file=sys.stderr)
        raise SystemExit(1) from None
