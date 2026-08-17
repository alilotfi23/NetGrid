from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import register_exception_handlers
from app.main import app


async def test_unknown_route_returns_error_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"]


async def test_method_not_allowed_returns_error_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


async def test_validation_error_returns_error_envelope_with_details():
    class Payload(BaseModel):
        count: int

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.post("/api/v1/echo")
    async def echo(payload: Payload) -> dict:
        return {"count": payload.count}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/api/v1/echo", json={"count": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in body["error"]


async def test_domain_error_uses_app_error_contract():
    from app.core.exceptions import NotFoundError

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/api/v1/missing")
    async def missing() -> None:
        raise NotFoundError("Subscriber 42 not found")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Subscriber 42 not found"
