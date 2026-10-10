"""Interfaces (puertos de la arquitectura hexagonal) que implementa la infraestructura."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Redirect


@dataclass(frozen=True, slots=True)
class ProxyStats:
    clients: int = 0
    bytes_in: int = 0  # cliente -> servidor TS3
    bytes_out: int = 0  # servidor TS3 -> cliente


class ForwardingEngine(Protocol):
    """Strategy: cómo se reenvía el tráfico UDP (asyncio, nftables...)."""

    async def start(self, redirect: Redirect) -> None:
        """Arranca (o reinicia con el destino actual) el proxy del puerto de la redirección."""
        ...

    async def stop(self, redirect: Redirect) -> None: ...

    def is_running(self, port: int) -> bool: ...

    def stats(self, port: int) -> ProxyStats | None: ...

    async def stop_all(self) -> None: ...


class Resolver(Protocol):
    """Adapter: traduce un host TS3 (dominio o IP) a (ip, puerto)."""

    async def resolve(self, host: str, port: int | None) -> tuple[str, int]: ...


class RedirectRepository(Protocol):
    async def allocate_and_insert(
        self, build: Callable[[int], Redirect], choose_port: Callable[[set[int]], int]
    ) -> Redirect:
        """En una única transacción: lee los puertos usados, elige uno con
        `choose_port(usados)` (que puede lanzar PortRangeExhausted) e inserta la
        redirección construida por `build(puerto)`."""
        ...

    async def list(self) -> Sequence[Redirect]: ...

    async def get(self, redirect_id: int) -> Redirect | None: ...

    async def update(self, redirect: Redirect) -> None: ...

    async def delete(self, redirect_id: int) -> bool: ...

    async def used_ports(self) -> set[int]: ...
