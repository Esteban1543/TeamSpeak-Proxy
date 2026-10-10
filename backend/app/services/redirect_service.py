"""Casos de uso de las redirecciones."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.domain.errors import EngineError, RedirectNotFound
from app.domain.models import Redirect, RedirectStatus, parse_target, utcnow
from app.domain.ports import ForwardingEngine, ProxyStats, RedirectRepository, Resolver
from app.services.port_allocator import PortAllocator, PortUsage

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RedirectView:
    redirect: Redirect
    stats: ProxyStats | None


class RedirectService:
    def __init__(
        self,
        repository: RedirectRepository,
        resolver: Resolver,
        engine: ForwardingEngine,
        allocator: PortAllocator,
    ) -> None:
        self._repo = repository
        self._resolver = resolver
        self._engine = engine
        self._allocator = allocator
        # Serializa cambios de estado (crear/borrar/reconciliar) sobre el motor.
        self.lock = asyncio.Lock()

    async def create(self, raw_target: str) -> RedirectView:
        target = parse_target(raw_target)
        ip, port = await self._resolver.resolve(target.host, target.port)
        now = utcnow()

        def build(public_port: int) -> Redirect:
            return Redirect(
                target_raw=target.raw,
                target_host=target.host,
                target_port=target.port,
                is_domain=target.is_domain,
                resolved_ip=ip,
                resolved_port=port,
                port=public_port,
                created_at=now,
                updated_at=now,
                resolved_at=now if target.is_domain else None,
            )

        async with self.lock:
            redirect = await self._repo.allocate_and_insert(build, self._allocator.choose)
            log.info("Redirección #%s creada: :%s -> %s (%s:%s)", redirect.id, redirect.port, target.raw, ip, port)
            await self.activate(redirect)
        return self._view(redirect)

    async def activate(self, redirect: Redirect) -> None:
        """Arranca el proxy y persiste el estado resultante (active / error)."""
        try:
            await self._engine.start(redirect)
        except EngineError as exc:
            if redirect.status != RedirectStatus.ERROR or redirect.error != exc.message:
                log.warning("Redirección #%s: %s", redirect.id, exc.message)
                redirect.transition_to(RedirectStatus.ERROR, exc.message)
                await self._repo.update(redirect)
            return
        if redirect.status != RedirectStatus.ACTIVE:
            redirect.transition_to(RedirectStatus.ACTIVE)
            await self._repo.update(redirect)

    async def list(self) -> list[RedirectView]:
        return [self._view(r) for r in await self._repo.list()]

    async def delete(self, redirect_id: int) -> None:
        async with self.lock:
            redirect = await self._repo.get(redirect_id)
            if redirect is None:
                raise RedirectNotFound(f"La redirección #{redirect_id} no existe")
            await self._engine.stop(redirect)
            await self._repo.delete(redirect_id)
            log.info("Redirección #%s eliminada, puerto %s liberado", redirect_id, redirect.port)

    async def port_usage(self) -> PortUsage:
        return self._allocator.usage(await self._repo.used_ports())

    def _view(self, redirect: Redirect) -> RedirectView:
        return RedirectView(redirect=redirect, stats=self._engine.stats(redirect.port))
