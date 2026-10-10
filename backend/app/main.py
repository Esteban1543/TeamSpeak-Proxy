"""Punto de entrada: crea la app FastAPI y gestiona arranque/apagado."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api import auth, redirects
from app.api.deps import Container
from app.config import Settings, get_settings
from app.domain.errors import (
    DomainError,
    EngineError,
    InvalidAlias,
    InvalidTarget,
    InvalidTransition,
    PortRangeExhausted,
    RedirectNotFound,
    ResolveError,
)
from app.domain.ports import ForwardingEngine, Resolver
from app.infrastructure.db.database import Database
from app.infrastructure.db.redirect_repository import SqliteRedirectRepository
from app.infrastructure.dns.ts3_resolver import Ts3DnsResolver
from app.infrastructure.forwarding import create_engine
from app.services.auth_service import AuthService
from app.services.port_allocator import PortAllocator
from app.services.reconciler import Reconciler
from app.services.redirect_service import RedirectService

log = logging.getLogger("app")

_ERROR_STATUS: dict[type[DomainError], int] = {
    InvalidTarget: status.HTTP_400_BAD_REQUEST,
    InvalidAlias: status.HTTP_400_BAD_REQUEST,
    ResolveError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    PortRangeExhausted: status.HTTP_409_CONFLICT,
    RedirectNotFound: status.HTTP_404_NOT_FOUND,
    InvalidTransition: status.HTTP_409_CONFLICT,
    EngineError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def create_app(
    settings: Settings | None = None,
    *,
    resolver: Resolver | None = None,
    engine: ForwardingEngine | None = None,
) -> FastAPI:
    """`resolver` y `engine` se pueden inyectar en los tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or get_settings()
        db = Database(cfg.database_path)
        await db.connect()
        repo = SqliteRedirectRepository(db)
        res = resolver or Ts3DnsResolver()
        eng = engine or create_engine(cfg)
        service = RedirectService(repo, res, eng, PortAllocator(cfg.port_range))
        reconciler = Reconciler(repo, res, eng, service, dns_refresh_seconds=cfg.dns_refresh_minutes * 60)
        app.state.container = Container(
            settings=cfg,
            auth=AuthService(cfg.admin_user, cfg.admin_password_hash, cfg.session_secret, cfg.session_expire_hours),
            redirects=service,
        )
        log.info(
            "Arrancando: rango %s-%s, host público %s, motor %s",
            cfg.port_range_start, cfg.port_range_end, cfg.public_host, cfg.forwarding_engine,
        )
        await reconciler.start()
        try:
            yield
        finally:
            await reconciler.stop()
            await eng.stop_all()
            await db.close()
            log.info("Apagado completo")

    app = FastAPI(
        title="TS3 Proxy Panel API",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        code = next((c for t, c in _ERROR_STATUS.items() if isinstance(exc, t)), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(status_code=code, content={"detail": exc.message, "code": type(exc).__name__})

    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(redirects.router)
    return app


def run() -> None:
    """`python -m app.main`: arranca uvicorn con uvloop y la configuración del .env."""
    import uvicorn

    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        loop="uvloop",
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        log_config=None,
    )


if __name__ == "__main__":
    run()
