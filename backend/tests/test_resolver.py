"""Ts3DnsResolver con las respuestas de dnspython simuladas."""

from types import SimpleNamespace

import dns.name
import dns.rdatatype
import dns.resolver
import pytest

from app.domain.errors import ResolveError
from app.infrastructure.dns.ts3_resolver import Ts3DnsResolver


class FakeDns:
    def __init__(self, records: dict[tuple[str, int], list]) -> None:
        self.records = records
        self.queries: list[tuple[str, int]] = []

    async def resolve(self, name: str, rdtype):
        self.queries.append((name, rdtype))
        if (name, rdtype) not in self.records:
            raise dns.resolver.NXDOMAIN()
        return self.records[(name, rdtype)]


def srv(target: str, port: int, priority: int = 10, weight: int = 0):
    return SimpleNamespace(target=dns.name.from_text(target), port=port, priority=priority, weight=weight)


def addr(ip: str):
    return SimpleNamespace(to_text=lambda: ip)


def make(records) -> tuple[Ts3DnsResolver, FakeDns]:
    r = Ts3DnsResolver()
    fake = FakeDns(records)
    r._resolver = fake  # type: ignore[assignment]
    return r, fake


async def test_ip_is_returned_without_dns():
    r, fake = make({})
    assert await r.resolve("1.2.3.4", None) == ("1.2.3.4", 9987)
    assert not fake.queries


async def test_srv_preferred():
    r, _ = make({
        ("_ts3._udp.ejemplo.com", dns.rdatatype.SRV): [srv("voz.ejemplo.com.", 9000, priority=20), srv("ts.ejemplo.com.", 9988)],
        ("ts.ejemplo.com", dns.rdatatype.A): [addr("5.6.7.8")],
        ("ejemplo.com", dns.rdatatype.A): [addr("9.9.9.9")],
    })
    assert await r.resolve("ejemplo.com", None) == ("5.6.7.8", 9988)


async def test_explicit_port_skips_srv_and_falls_back_to_aaaa():
    r, fake = make({("ejemplo.com", dns.rdatatype.AAAA): [addr("2001:db8::2")]})
    assert await r.resolve("ejemplo.com", 1234) == ("2001:db8::2", 1234)
    assert all(q[1] != dns.rdatatype.SRV for q in fake.queries)


async def test_a_record_stable_order():
    r, _ = make({("ejemplo.com", dns.rdatatype.A): [addr("9.0.0.2"), addr("9.0.0.1")]})
    assert await r.resolve("ejemplo.com", None) == ("9.0.0.1", 9987)


async def test_not_found():
    r, _ = make({})
    with pytest.raises(ResolveError):
        await r.resolve("noexiste.com", None)
