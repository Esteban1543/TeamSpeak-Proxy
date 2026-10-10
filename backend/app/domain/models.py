"""Entidades y reglas del dominio: redirecciones, estados y parseo de destinos."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.domain.errors import InvalidTarget, InvalidTransition

DEFAULT_TS3_PORT = 9987


class RedirectStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    STOPPED = "stopped"


# Patrón State: transiciones válidas entre estados.
ALLOWED_TRANSITIONS: dict[RedirectStatus, frozenset[RedirectStatus]] = {
    RedirectStatus.PENDING: frozenset({RedirectStatus.ACTIVE, RedirectStatus.ERROR, RedirectStatus.STOPPED}),
    RedirectStatus.ACTIVE: frozenset({RedirectStatus.ERROR, RedirectStatus.STOPPED, RedirectStatus.PENDING}),
    RedirectStatus.ERROR: frozenset({RedirectStatus.ACTIVE, RedirectStatus.STOPPED, RedirectStatus.PENDING}),
    RedirectStatus.STOPPED: frozenset({RedirectStatus.PENDING}),
}


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Target:
    """Destino tal como lo escribió el administrador, ya validado."""

    raw: str
    host: str
    port: int | None  # None = no indicado (usar SRV o 9987)
    is_domain: bool


@dataclass(slots=True)
class Redirect:
    target_raw: str
    target_host: str
    target_port: int | None
    is_domain: bool
    resolved_ip: str
    resolved_port: int
    port: int
    status: RedirectStatus = RedirectStatus.PENDING
    error: str | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    resolved_at: datetime | None = None

    def transition_to(self, new: RedirectStatus, error: str | None = None) -> None:
        if new != self.status and new not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidTransition(f"No se puede pasar de '{self.status}' a '{new}'")
        self.status = new
        self.error = error if new == RedirectStatus.ERROR else None
        self.updated_at = utcnow()


_HOSTNAME_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def _parse_port(value: str) -> int:
    if not value.isdigit():
        raise InvalidTarget(f"Puerto inválido: '{value}'")
    port = int(value)
    if not 1 <= port <= 65535:
        raise InvalidTarget(f"El puerto debe estar entre 1 y 65535 (recibido {port})")
    return port


def _is_valid_hostname(host: str) -> bool:
    if len(host) > 253 or "." not in host:
        return False
    labels = host.split(".")
    if labels[-1].isdigit():  # parece una IP mal escrita
        return False
    return all(_HOSTNAME_LABEL.match(label) for label in labels)


def parse_target(raw: str) -> Target:
    """Acepta `IP`, `IP:puerto`, `[IPv6]:puerto`, `IPv6`, `dominio` o `dominio:puerto`."""
    text = raw.strip()
    if not text:
        raise InvalidTarget("El destino está vacío")
    if len(text) > 260:
        raise InvalidTarget("El destino es demasiado largo")
    if "://" in text or "/" in text or " " in text:
        raise InvalidTarget("Escribe solo IP:puerto o dominio, sin esquema ni rutas")

    host: str
    port: int | None = None

    if text.startswith("["):
        m = re.fullmatch(r"\[([^\]]+)\](?::(\d+))?", text)
        if not m:
            raise InvalidTarget("Formato IPv6 inválido; usa [IPv6]:puerto")
        host, port_s = m.group(1), m.group(2)
        port = _parse_port(port_s) if port_s else None
    elif text.count(":") > 1:
        host = text  # IPv6 sin puerto
    elif ":" in text:
        host, port_s = text.rsplit(":", 1)
        port = _parse_port(port_s)
    else:
        host = text

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        host = host.lower().rstrip(".")
        if not _is_valid_hostname(host):
            raise InvalidTarget(f"'{host}' no es una IP ni un dominio válido") from None
        return Target(raw=text, host=host, port=port, is_domain=True)

    if ip.is_unspecified or ip.is_multicast:
        raise InvalidTarget(f"La IP {ip} no es un destino válido")
    return Target(raw=text, host=str(ip), port=port, is_domain=False)
