from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import RedirectStatus
from app.services.port_allocator import PortUsage
from app.services.redirect_service import RedirectView


class RedirectCreate(BaseModel):
    target: str = Field(min_length=1, max_length=260, examples=["ts.ejemplo.com", "1.2.3.4:9987"])


class RedirectOut(BaseModel):
    id: int
    target: str
    is_domain: bool
    resolved_ip: str
    resolved_port: int
    resolved_address: str
    port: int
    public_address: str
    status: RedirectStatus
    error: str | None
    created_at: datetime
    resolved_at: datetime | None
    clients: int
    bytes_in: int
    bytes_out: int

    @classmethod
    def from_view(cls, view: RedirectView, public_host: str) -> RedirectOut:
        r, s = view.redirect, view.stats
        return cls(
            id=r.id,  # type: ignore[arg-type]
            target=r.target_raw,
            is_domain=r.is_domain,
            resolved_ip=r.resolved_ip,
            resolved_port=r.resolved_port,
            resolved_address=_join(r.resolved_ip, r.resolved_port),
            port=r.port,
            public_address=_join(public_host, r.port),
            status=r.status,
            error=r.error,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
            clients=s.clients if s else 0,
            bytes_in=s.bytes_in if s else 0,
            bytes_out=s.bytes_out if s else 0,
        )


class PortUsageOut(BaseModel):
    public_host: str
    used: int
    total: int
    free: int
    range_start: int
    range_end: int

    @classmethod
    def from_usage(cls, u: PortUsage, public_host: str) -> PortUsageOut:
        return cls(
            public_host=public_host,
            used=u.used,
            total=u.total,
            free=u.free,
            range_start=u.range_start,
            range_end=u.range_end,
        )


def _join(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
