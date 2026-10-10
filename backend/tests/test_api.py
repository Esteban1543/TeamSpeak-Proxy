"""Flujo completo de la API con BD real (SQLite temporal) y proxy asyncio real."""

import asyncio

import httpx
import pytest

from app.domain.models import RedirectStatus
from app.infrastructure.forwarding.asyncio_proxy import AsyncioForwardingEngine
from app.main import create_app
from tests.conftest import PASSWORD, FakeResolver, make_settings


class LifespanClient:
    def __init__(self, app):
        self.app = app

    async def __aenter__(self) -> httpx.AsyncClient:
        self._ctx = self.app.router.lifespan_context(self.app)
        await self._ctx.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        return self.client

    async def __aexit__(self, *exc):
        await self.client.aclose()
        await self._ctx.__aexit__(*exc)


def build_app(settings, resolver=None):
    engine = AsyncioForwardingEngine(bind_host="127.0.0.1")
    app = create_app(settings, resolver=resolver or FakeResolver({"ts.ejemplo.com": ("127.0.0.1", 9999)}), engine=engine)
    return app, engine


async def login(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200, r.text


async def test_auth_required_and_login(settings):
    app, _ = build_app(settings)
    async with LifespanClient(app) as client:
        assert (await client.get("/api/redirects")).status_code == 401
        assert (await client.get("/api/auth/me")).status_code == 401
        bad = await client.post("/api/auth/login", json={"username": "admin", "password": "mal"})
        assert bad.status_code == 401
        await login(client)
        me = await client.get("/api/auth/me")
        assert me.json() == {"username": "admin"}
        cookie = me.request.headers["cookie"]
        assert "ts3proxy_session" in cookie
        assert (await client.post("/api/auth/logout")).status_code == 204
        client.cookies.clear()
        assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_throttle(settings):
    app, _ = build_app(settings)
    async with LifespanClient(app) as client:
        for _ in range(5):
            await client.post("/api/auth/login", json={"username": "admin", "password": "mal"})
        r = await client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
        assert r.status_code == 429


async def test_redirect_lifecycle(settings):
    app, engine = build_app(settings)
    async with LifespanClient(app) as client:
        await login(client)

        r = await client.post("/api/redirects", json={"target": "ts.ejemplo.com"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["port"] == 41000
        assert body["public_address"] == "203.0.113.10:41000"
        assert body["resolved_address"] == "127.0.0.1:9999"
        assert body["status"] == "active"
        assert engine.is_running(41000)

        assert (await client.post("/api/redirects", json={"target": "1.2.3.4"})).json()["resolved_port"] == 9987
        assert (await client.post("/api/redirects", json={"target": "1.2.3.4:9988"})).json()["port"] == 41002

        full = await client.post("/api/redirects", json={"target": "1.2.3.5"})
        assert full.status_code == 409
        assert "No quedan puertos" in full.json()["detail"]

        usage = (await client.get("/api/ports/usage")).json()
        assert usage == {"public_host": "203.0.113.10", "used": 3, "total": 3, "free": 0, "range_start": 41000, "range_end": 41002}

        assert (await client.post("/api/redirects", json={"target": "noexiste.com"})).status_code == 422
        assert (await client.post("/api/redirects", json={"target": "a b"})).status_code == 400

        assert (await client.delete(f"/api/redirects/{body['id']}")).status_code == 204
        assert not engine.is_running(41000)
        assert (await client.delete(f"/api/redirects/{body['id']}")).status_code == 404

        again = await client.post("/api/redirects", json={"target": "1.2.3.6"})
        assert again.json()["port"] == 41000
        assert len((await client.get("/api/redirects")).json()) == 3


async def test_concurrent_creation_gets_unique_ports(settings):
    app, _ = build_app(settings)
    async with LifespanClient(app) as client:
        await login(client)
        results = await asyncio.gather(
            *(client.post("/api/redirects", json={"target": f"10.0.0.{i}"}) for i in range(1, 6))
        )
        ok = [r.json()["port"] for r in results if r.status_code == 201]
        assert sorted(ok) == [41000, 41001, 41002]
        assert sum(r.status_code == 409 for r in results) == 2


async def test_redirects_restored_after_restart(tmp_path):
    settings = make_settings(tmp_path)
    app, engine = build_app(settings)
    async with LifespanClient(app) as client:
        await login(client)
        await client.post("/api/redirects", json={"target": "ts.ejemplo.com"})
        await client.post("/api/redirects", json={"target": "1.2.3.4"})
    assert not engine.is_running(41000)

    # "Reinicio": nueva app sobre la misma BD; el reconciliador relanza los proxies.
    app2, engine2 = build_app(settings, FakeResolver({"ts.ejemplo.com": ("127.0.0.2", 9999)}))
    async with LifespanClient(app2) as client:
        await login(client)
        assert engine2.is_running(41000) and engine2.is_running(41001)
        items = (await client.get("/api/redirects")).json()
        assert all(i["status"] == RedirectStatus.ACTIVE for i in items)

        # Re-resolución DNS: la IP del dominio cambió.
        container = app2.state.container
        from app.services.reconciler import Reconciler

        reconciler = Reconciler(
            container.redirects._repo, container.redirects._resolver, engine2, container.redirects, 600
        )
        await reconciler.refresh_dns()
        items = (await client.get("/api/redirects")).json()
        assert items[0]["resolved_ip"] == "127.0.0.2"


def test_settings_validation(tmp_path):
    with pytest.raises(Exception, match="PORT_RANGE_END"):
        make_settings(tmp_path, port_range_start=10100, port_range_end=10000)
    with pytest.raises(Exception, match="hash_password"):
        make_settings(tmp_path, admin_password_hash="")
