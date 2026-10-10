"""Factory del motor de reenvío según FORWARDING_ENGINE."""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import ForwardingEngine


def create_engine(settings: Settings) -> ForwardingEngine:
    match settings.forwarding_engine:
        case "asyncio":
            from app.infrastructure.forwarding.asyncio_proxy import AsyncioForwardingEngine

            return AsyncioForwardingEngine(idle_timeout=settings.client_idle_timeout)
        case "nftables":
            from app.infrastructure.forwarding.nftables import NftablesForwardingEngine

            return NftablesForwardingEngine()
    raise ValueError(f"Motor de reenvío desconocido: {settings.forwarding_engine}")
