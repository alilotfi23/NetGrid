import asyncio

from fastapi import Request, Response
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.models.rbac import Admin

LOGIN = {"username": "root", "password": "wrong"}


async def _seed_admin(session):
    session.add(
        Admin(
            username="root",
            email="root@netgrid.local",
            password_hash=hash_password("secret123"),
            is_active=True,
        )
    )
    await session.commit()


async def test_login_locked_out_after_threshold(app, session):
    await _seed_admin(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.post("/api/v1/auth/login", json=LOGIN)
            assert resp.status_code == 401
        resp = await client.post("/api/v1/auth/login", json=LOGIN)
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"
        assert resp.headers.get("Retry-After") is not None


async def test_rate_limit_is_per_ip(app, session):
    await _seed_admin(session)
    client_a = AsyncClient(
        transport=ASGITransport(app=app, client=("10.1.1.1", 1)), base_url="http://test"
    )
    client_b = AsyncClient(
        transport=ASGITransport(app=app, client=("10.2.2.2", 2)), base_url="http://test"
    )
    async with client_a, client_b:
        # A exhausts its own 5/min budget: 5 rejected attempts, then a 429.
        for _ in range(5):
            assert (await client_a.post("/api/v1/auth/login", json=LOGIN)).status_code == 401
        assert (await client_a.post("/api/v1/auth/login", json=LOGIN)).status_code == 429
        # B is a different IP: untouched by A's lockout, still gets a normal 401.
        assert (await client_b.post("/api/v1/auth/login", json=LOGIN)).status_code == 401


async def test_limit_resets_after_window(app):
    @app.get("/api/v1/scratch")
    @limiter.limit("2/second")
    async def scratch(request: Request, response: Response):
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/scratch")).status_code == 200
        assert (await client.get("/api/v1/scratch")).status_code == 200
        assert (await client.get("/api/v1/scratch")).status_code == 429
        # Poll until the 1s window rolls over (bounded, so slow CI machines
        # don't flake on a fixed sleep).
        recovered = False
        for _ in range(30):
            await asyncio.sleep(0.2)
            if (await client.get("/api/v1/scratch")).status_code == 200:
                recovered = True
                break
        assert recovered
