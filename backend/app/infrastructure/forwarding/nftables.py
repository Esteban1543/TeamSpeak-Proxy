"""Motor de reenvío basado en nftables (DNAT/SNAT en el kernel). Pendiente.

Idea de implementación futura:
- Una tabla propia, p. ej. `table ip ts3proxy`, con cadenas `prerouting` (DNAT
  `udp dport <puerto> dnat to <ip>:<puerto_ts3>`) y `postrouting` (masquerade).
- `start()` / `stop()` añaden o borran reglas con handles guardados por puerto.
- Requiere `net.ipv4.ip_forward=1` y `cap_add: [NET_ADMIN]` en docker-compose.
- Ventaja: reenvío en el kernel, latencia y CPU mínimas. Inconveniente: sin
  estadísticas por cliente salvo con contadores de nftables.
"""

from __future__ import annotations

from app.domain.models import Redirect
from app.domain.ports import ProxyStats


class NftablesForwardingEngine:
    def __init__(self) -> None:
        raise NotImplementedError(
            "FORWARDING_ENGINE=nftables todavía no está implementado; usa FORWARDING_ENGINE=asyncio"
        )

    async def start(self, redirect: Redirect) -> None:  # pragma: no cover
        raise NotImplementedError

    async def stop(self, redirect: Redirect) -> None:  # pragma: no cover
        raise NotImplementedError

    def is_running(self, port: int) -> bool:  # pragma: no cover
        raise NotImplementedError

    def stats(self, port: int) -> ProxyStats | None:  # pragma: no cover
        raise NotImplementedError

    async def stop_all(self) -> None:  # pragma: no cover
        raise NotImplementedError
