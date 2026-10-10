"""Sincroniza la BD con los proxies en ejecución y re-resuelve los dominios.

- Al arrancar: levanta todas las redirecciones que no estén `stopped`.
- Cada HEALTH_INTERVAL segundos: relanza proxies caídos o en error.
- Cada DNS_REFRESH_MINUTES: re-resuelve los dominios y actualiza la IP si cambió.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.domain.errors import DomainError
from app.domain.models import RedirectStatus, utcnow
from app.domain.ports import ForwardingEngine, RedirectRepository, Resolver
from app.services.redirect_service import RedirectService

log = logging.getLogger(__name__)

HEALTH_INTERVAL = 30.0


class Reconciler:
    def __init__(
        self,
        repository: RedirectRepository,
        resolver: Resolver,
        engine: ForwardingEngine,
        service: RedirectService,
        dns_refresh_seconds: float,
    ) -> None:
        self._repo = repository
        self._resolver = resolver
        self._engine = engine
        self._service = service
        self._dns_refresh = dns_refresh_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.ensure_running()
        self._task = asyncio.create_task(self._loop(), name="reconciler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        last_dns = time.monotonic()
        while True:
            await asyncio.sleep(HEALTH_INTERVAL)
            try:
                if time.monotonic() - last_dns >= self._dns_refresh:
                    last_dns = time.monotonic()
                    await self.refresh_dns()
                await self.ensure_running()
            except Exception:
                log.exception("Error en el ciclo del reconciliador")

    async def ensure_running(self) -> None:
        async with self._service.lock:
            redirects = await self._repo.list()
            started = 0
            for redirect in redirects:
                if redirect.status == RedirectStatus.STOPPED:
                    continue
                if self._engine.is_running(redirect.port) and redirect.status == RedirectStatus.ACTIVE:
                    continue
                was_running = self._engine.is_running(redirect.port)
                await self._service.activate(redirect)
                if not was_running and redirect.status == RedirectStatus.ACTIVE:
                    started += 1
            if started:
                log.info("Reconciliador: %s proxy(s) levantado(s)", started)

    async def refresh_dns(self) -> None:
        for redirect in await self._repo.list():
            if not redirect.is_domain or redirect.status == RedirectStatus.STOPPED:
                continue
            try:
                ip, port = await self._resolver.resolve(redirect.target_host, redirect.target_port)
            except DomainError as exc:
                # Se mantiene la última IP conocida: mejor que cortar un proxy que funciona.
                log.warning("No se pudo re-resolver %s: %s", redirect.target_raw, exc.message)
                continue

            async with self._service.lock:
                current = await self._repo.get(redirect.id)  # type: ignore[arg-type]
                if current is None:  # eliminada mientras resolvíamos
                    continue
                current.resolved_at = utcnow()
                changed = (current.resolved_ip, current.resolved_port) != (ip, port)
                if changed:
                    log.info(
                        "%s cambió de %s:%s a %s:%s",
                        current.target_raw, current.resolved_ip, current.resolved_port, ip, port,
                    )
                    current.resolved_ip, current.resolved_port = ip, port
                    current.updated_at = utcnow()
                await self._repo.update(current)
                if changed and current.status != RedirectStatus.STOPPED:
                    await self._service.activate(current)
