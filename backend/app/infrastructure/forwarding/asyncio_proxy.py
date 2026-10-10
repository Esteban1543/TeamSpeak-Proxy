"""Motor de reenvío UDP en espacio de usuario con asyncio (+ uvloop).

Por cada redirección se escucha en `0.0.0.0:<puerto>`. Cada cliente (IP:puerto de
origen) obtiene su propio socket de salida hacia el servidor TS3, de modo que las
respuestas se devuelven al cliente correcto y el servidor ve la IP de la VPS.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.domain.errors import EngineError
from app.domain.models import Redirect
from app.domain.ports import ProxyStats

log = logging.getLogger(__name__)

Addr = tuple[str, int]

SWEEP_INTERVAL = 30.0
MAX_PENDING_PACKETS = 64
MAX_SESSIONS_PER_PROXY = 1024


class _ClientSession(asyncio.DatagramProtocol):
    """Socket de salida dedicado a un cliente concreto."""

    def __init__(self, proxy: UdpProxy, client: Addr) -> None:
        self.proxy = proxy
        self.client = client
        self.transport: asyncio.DatagramTransport | None = None
        self.pending: list[bytes] = []
        self.last_seen = time.monotonic()
        self.closed = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: Addr) -> None:
        self.last_seen = time.monotonic()
        self.proxy.bytes_out += len(data)
        self.proxy.reply(data, self.client)

    def error_received(self, exc: Exception) -> None:
        # Normalmente ICMP "port unreachable": el servidor TS3 no responde.
        log.debug("Puerto %s, cliente %s: %s", self.proxy.port, self.client, exc)

    def connection_lost(self, exc: Exception | None) -> None:
        self.closed = True
        if self.proxy.sessions.get(self.client) is self:
            del self.proxy.sessions[self.client]

    def send(self, data: bytes) -> None:
        self.last_seen = time.monotonic()
        if self.transport is None:
            if len(self.pending) < MAX_PENDING_PACKETS:
                self.pending.append(data)
            return
        self.transport.sendto(data)

    def flush(self) -> None:
        assert self.transport is not None
        for data in self.pending:
            self.transport.sendto(data)
        self.pending.clear()

    def close(self) -> None:
        self.closed = True
        if self.transport is not None:
            self.transport.close()


class _ListenProtocol(asyncio.DatagramProtocol):
    def __init__(self, proxy: UdpProxy) -> None:
        self.proxy = proxy

    def datagram_received(self, data: bytes, addr: Addr) -> None:
        self.proxy.forward(data, (addr[0], addr[1]))

    def error_received(self, exc: Exception) -> None:
        log.debug("Puerto %s: error en socket de escucha: %s", self.proxy.port, exc)

    def connection_lost(self, exc: Exception | None) -> None:
        if not self.proxy.closing:
            log.warning("Puerto %s: socket de escucha cerrado inesperadamente (%s)", self.proxy.port, exc)
        self.proxy.listening = False


class UdpProxy:
    def __init__(self, port: int, target: Addr, idle_timeout: float, bind_host: str = "0.0.0.0") -> None:
        self.port = port
        self.target = target
        self.idle_timeout = idle_timeout
        self.bind_host = bind_host
        self.sessions: dict[Addr, _ClientSession] = {}
        self.bytes_in = 0
        self.bytes_out = 0
        self.listening = False
        self.closing = False
        self._transport: asyncio.DatagramTransport | None = None
        self._sweeper: asyncio.Task[None] | None = None
        self._connect_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _ListenProtocol(self), local_addr=(self.bind_host, self.port)
        )
        self._transport = transport
        self.listening = True
        self._sweeper = asyncio.create_task(self._sweep_loop(), name=f"udp-sweep-{self.port}")
        log.info("Proxy UDP :%s -> %s:%s", self.port, *self.target)

    def forward(self, data: bytes, client: Addr) -> None:
        self.bytes_in += len(data)
        session = self.sessions.get(client)
        if session is None:
            if len(self.sessions) >= MAX_SESSIONS_PER_PROXY:
                return
            session = _ClientSession(self, client)
            self.sessions[client] = session
            task = asyncio.create_task(self._connect(session))
            self._connect_tasks.add(task)
            task.add_done_callback(self._connect_tasks.discard)
        session.send(data)

    async def _connect(self, session: _ClientSession) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.create_datagram_endpoint(lambda: session, remote_addr=self.target)
        except OSError as exc:
            log.warning("Puerto %s: no se pudo abrir socket hacia %s: %s", self.port, self.target, exc)
            if self.sessions.get(session.client) is session:
                del self.sessions[session.client]
            return
        if session.closed or self.closing:
            session.close()
            return
        session.flush()

    def reply(self, data: bytes, client: Addr) -> None:
        if self._transport is not None and not self._transport.is_closing():
            self._transport.sendto(data, client)

    def set_target(self, target: Addr) -> None:
        if target == self.target:
            return
        log.info("Puerto %s: destino cambiado %s -> %s", self.port, self.target, target)
        self.target = target
        self._close_sessions()  # los clientes se reconectan al nuevo destino

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_INTERVAL)
            now = time.monotonic()
            for client, session in list(self.sessions.items()):
                if now - session.last_seen > self.idle_timeout:
                    log.debug("Puerto %s: cerrando sesión inactiva de %s", self.port, client)
                    session.close()
                    self.sessions.pop(client, None)

    def _close_sessions(self) -> None:
        for session in list(self.sessions.values()):
            session.close()
        self.sessions.clear()

    async def stop(self) -> None:
        self.closing = True
        if self._sweeper is not None:
            self._sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sweeper
        for task in list(self._connect_tasks):
            task.cancel()
        self._close_sessions()
        if self._transport is not None:
            self._transport.close()
        self.listening = False
        log.info("Proxy UDP :%s detenido", self.port)

    @property
    def running(self) -> bool:
        return self.listening and not self.closing

    def stats(self) -> ProxyStats:
        return ProxyStats(clients=len(self.sessions), bytes_in=self.bytes_in, bytes_out=self.bytes_out)


class AsyncioForwardingEngine:
    """Implementación de ForwardingEngine. Registry: puerto -> proxy activo."""

    def __init__(self, idle_timeout: float = 120.0, bind_host: str = "0.0.0.0") -> None:
        self._idle_timeout = idle_timeout
        self._bind_host = bind_host
        self._proxies: dict[int, UdpProxy] = {}
        self._lock = asyncio.Lock()

    async def start(self, redirect: Redirect) -> None:
        target = (redirect.resolved_ip, redirect.resolved_port)
        async with self._lock:
            proxy = self._proxies.get(redirect.port)
            if proxy is not None and proxy.running:
                proxy.set_target(target)
                return
            if proxy is not None:  # registrado pero caído: limpiar antes de relanzar
                await proxy.stop()
                del self._proxies[redirect.port]

            proxy = UdpProxy(redirect.port, target, self._idle_timeout, self._bind_host)
            try:
                await proxy.start()
            except OSError as exc:
                raise EngineError(f"No se pudo escuchar en el puerto UDP {redirect.port}: {exc.strerror or exc}") from exc
            self._proxies[redirect.port] = proxy

    async def stop(self, redirect: Redirect) -> None:
        async with self._lock:
            proxy = self._proxies.pop(redirect.port, None)
            if proxy is not None:
                await proxy.stop()

    def is_running(self, port: int) -> bool:
        proxy = self._proxies.get(port)
        return proxy is not None and proxy.running

    def stats(self, port: int) -> ProxyStats | None:
        proxy = self._proxies.get(port)
        return proxy.stats() if proxy is not None else None

    async def stop_all(self) -> None:
        async with self._lock:
            proxies, self._proxies = list(self._proxies.values()), {}
        for proxy in proxies:
            await proxy.stop()
