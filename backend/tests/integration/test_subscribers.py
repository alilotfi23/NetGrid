"""Integration tests for the subscribers stats endpoint (Phase 5, partial)."""

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.rbac import Admin, Permission, Role
from app.models.subscriber import Subscriber


async def _seed_admin(session, username, codes):
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    role = Role(name=f"role_{username}")
    role.permissions = [Permission(code=code) for code in codes]
    admin.roles.append(role)
    session.add(admin)
    await session.commit()
    return admin


async def _login(client, username="boss"):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_stats_returns_counts_for_reader(client, session):
    session.add_all(
        [
            Subscriber(username="a1", full_name="A One", status="active"),
            Subscriber(username="a2", full_name="A Two", status="active"),
            Subscriber(username="s1", full_name="S One", status="suspended"),
            Subscriber(username="e1", full_name="E One", status="expired"),
        ]
    )
    await session.commit()

    await _seed_admin(session, "boss", ["subscribers:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/subscribers/stats", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"active": 2, "suspended": 1, "expired": 1, "total": 4}


async def test_stats_empty_db(client, session):
    await _seed_admin(session, "boss", ["subscribers:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/subscribers/stats", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"active": 0, "suspended": 0, "expired": 0, "total": 0}


async def test_stats_requires_authentication(client, session):
    resp = await client.get("/api/v1/subscribers/stats")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_stats_denied_without_permission_and_audited(client, session):
    await _seed_admin(session, "nope", ["plans:read"])
    token = await _login(client, "nope")
    resp = await client.get("/api/v1/subscribers/stats", headers=_auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

    rows = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "permission_denied")))
        .scalars()
        .all()
    )
    assert any(
        r.metadata_ == {"permission": "subscribers:read", "path": "/api/v1/subscribers/stats"}
        for r in rows
    )


async def test_stats_allowed_request_not_logged_as_denial(client, session):
    await _seed_admin(session, "boss", ["subscribers:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/subscribers/stats", headers=_auth(token))
    assert resp.status_code == 200
    rows = (
        await session.execute(select(AuditLog).where(AuditLog.action == "permission_denied"))
    ).scalars()
    assert rows.all() == []
