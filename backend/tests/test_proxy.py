"""Proxy UDP de extremo a extremo: cliente -> proxy -> servidor eco -> proxy -> cliente."""

import asyncio
import socket

import pytest

from app.domain.errors import EngineError
from app.domain.models import Redirect
from app.infrastructure.forwarding.asyncio_proxy import AsyncioForwardingEngine


class Echo(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.peers: list[tuple[str, int]] = []

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.peers.append(addr)
        self.transport.sendto(b"echo:" + data, addr)


class Client(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.queue.put_nowait(data)


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_forwarding_roundtrip_and_stats():
    loop = asyncio.get_running_loop()
    echo_tr, echo = await loop.create_datagram_endpoint(Echo, local_addr=("127.0.0.1", 0))
    echo_port = echo_tr.get_extra_info("sockname")[1]

    engine = AsyncioForwardingEngine(idle_timeout=60, bind_host="127.0.0.1")
    proxy_port = free_udp_port()
    redirect = Redirect("x", "127.0.0.1", None, False, "127.0.0.1", echo_port, proxy_port, id=1)
    await engine.start(redirect)
    assert engine.is_running(proxy_port)

    clients = []
    for i in range(2):
        tr, c = await loop.create_datagram_endpoint(Client, remote_addr=("127.0.0.1", proxy_port))
        clients.append((tr, c))
        tr.sendto(f"hola{i}".encode())
    for i, (_, c) in enumerate(clients):
        assert await asyncio.wait_for(c.queue.get(), 2) == f"echo:hola{i}".encode()

    # El servidor ve los sockets del proxy, no los de los clientes.
    client_ports = {tr.get_extra_info("sockname")[1] for tr, _ in clients}
    assert len(set(echo.peers)) == 2
    assert not client_ports & {p for _, p in echo.peers}

    stats = engine.stats(proxy_port)
    assert stats.clients == 2
    assert stats.bytes_in == len(b"hola0") * 2
    assert stats.bytes_out == len(b"echo:hola0") * 2

    # Cambio de destino: las sesiones se reinician y el tráfico va al nuevo servidor.
    echo2_tr, echo2 = await loop.create_datagram_endpoint(Echo, local_addr=("127.0.0.1", 0))
    redirect.resolved_port = echo2_tr.get_extra_info("sockname")[1]
    await engine.start(redirect)
    clients[0][0].sendto(b"otra")
    assert await asyncio.wait_for(clients[0][1].queue.get(), 2) == b"echo:otra"
    assert echo2.peers

    await engine.stop(redirect)
    assert not engine.is_running(proxy_port)
    for tr, _ in clients:
        tr.close()
    echo_tr.close()
    echo2_tr.close()


async def test_port_in_use_raises_engine_error():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as busy:
        busy.bind(("127.0.0.1", 0))
        port = busy.getsockname()[1]
        engine = AsyncioForwardingEngine(bind_host="127.0.0.1")
        with pytest.raises(EngineError):
            await engine.start(Redirect("x", "x", None, False, "127.0.0.1", 9, port, id=1))
        assert not engine.is_running(port)


async def test_idle_sessions_are_swept(monkeypatch):
    from app.infrastructure.forwarding import asyncio_proxy

    monkeypatch.setattr(asyncio_proxy, "SWEEP_INTERVAL", 0.1)
    loop = asyncio.get_running_loop()
    echo_tr, _ = await loop.create_datagram_endpoint(Echo, local_addr=("127.0.0.1", 0))
    engine = AsyncioForwardingEngine(idle_timeout=0.3, bind_host="127.0.0.1")
    port = free_udp_port()
    redirect = Redirect("x", "127.0.0.1", None, False, "127.0.0.1", echo_tr.get_extra_info("sockname")[1], port, id=1)
    await engine.start(redirect)

    tr, c = await loop.create_datagram_endpoint(Client, remote_addr=("127.0.0.1", port))
    tr.sendto(b"ping")
    await asyncio.wait_for(c.queue.get(), 2)
    assert engine.stats(port).clients == 1

    # Sin tráfico más allá del timeout, la sesión se cierra y el contador baja.
    await asyncio.sleep(0.6)
    assert engine.stats(port).clients == 0
    # Las estadísticas de tráfico acumuladas se conservan.
    assert engine.stats(port).bytes_in == 4

    await engine.stop(redirect)
    tr.close()
    echo_tr.close()
