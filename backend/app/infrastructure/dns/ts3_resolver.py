"""Adapter sobre dnspython: resuelve un host TS3 a (ip, puerto).

Orden (igual que el cliente de TeamSpeak 3):
1. Si es una IP, se devuelve tal cual.
2. Si no se indicó puerto, se consulta SRV `_ts3._udp.<dominio>`.
3. Si no hay SRV (o se indicó puerto), A y luego AAAA.
"""

from __future__ import annotations

import ipaddress
import logging

import dns.asyncresolver
import dns.exception
import dns.rdatatype
import dns.resolver

from app.domain.errors import ResolveError
from app.domain.models import DEFAULT_TS3_PORT

log = logging.getLogger(__name__)

_NOT_FOUND = (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers)


class Ts3DnsResolver:
    def __init__(self, timeout: float = 5.0) -> None:
        self._resolver = dns.asyncresolver.Resolver()
        self._resolver.lifetime = timeout

    async def resolve(self, host: str, port: int | None) -> tuple[str, int]:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return host, port or DEFAULT_TS3_PORT

        if port is None:
            srv = await self._lookup_srv(host)
            if srv is not None:
                srv_host, srv_port = srv
                ip = await self._lookup_address(srv_host)
                if ip is None:
                    raise ResolveError(f"El registro SRV de {host} apunta a {srv_host}, que no resuelve")
                return ip, srv_port

        ip = await self._lookup_address(host)
        if ip is None:
            raise ResolveError(f"No se encontró ningún registro SRV, A ni AAAA para {host}")
        return ip, port or DEFAULT_TS3_PORT

    async def _lookup_srv(self, host: str) -> tuple[str, int] | None:
        try:
            answer = await self._resolver.resolve(f"_ts3._udp.{host}", dns.rdatatype.SRV)
        except _NOT_FOUND:
            return None
        except dns.exception.Timeout as exc:
            raise ResolveError(f"Tiempo de espera agotado consultando SRV de {host}") from exc

        records = list(answer)
        if not records:
            return None
        # Selección determinista (menor prioridad, mayor peso, nombre) para que la
        # re-resolución periódica no alterne entre registros y reinicie el proxy.
        chosen = min(records, key=lambda r: (r.priority, -r.weight, r.target.to_text(), r.port))
        target = chosen.target.to_text(omit_final_dot=True)
        if target in ("", "."):
            return None
        log.debug("SRV %s -> %s:%s", host, target, chosen.port)
        return target, int(chosen.port)

    async def _lookup_address(self, host: str) -> str | None:
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass
        for rdtype in (dns.rdatatype.A, dns.rdatatype.AAAA):
            try:
                answer = await self._resolver.resolve(host, rdtype)
            except _NOT_FOUND:
                continue
            except dns.exception.Timeout as exc:
                raise ResolveError(f"Tiempo de espera agotado resolviendo {host}") from exc
            # Orden estable: con DNS round-robin evita cambiar de IP en cada refresco.
            addresses = sorted(record.to_text() for record in answer)
            if addresses:
                return addresses[0]
        return None
