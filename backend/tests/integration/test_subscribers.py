"""Integration tests for the subscribers API (Phase 5)."""

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.radius import RadCheck
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


async def _radcheck_rows(session, username: str, attribute: str | None = None) -> list[RadCheck]:
    stmt = select(RadCheck).where(RadCheck.username == username)
    if attribute is not None:
        stmt = stmt.where(RadCheck.attribute == attribute)
    return list((await session.execute(stmt)).scalars().all())


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


async def test_superadmin_full_lifecycle(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob Subscriber", "password": "radpass123"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    subscriber_id = body["id"]
    assert body["username"] == "bob"
    assert body["status"] == "active"
    assert body["plan_id"] is None

    # radcheck carries the credential
    password_rows = await _radcheck_rows(session, "bob", "Cleartext-Password")
    assert len(password_rows) == 1
    assert password_rows[0].value == "radpass123"

    resp = await client.get("/api/v1/subscribers", headers=_auth(token))
    assert resp.status_code == 200
    assert "bob" in [s["username"] for s in resp.json()["items"]]

    resp = await client.get(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))
    assert resp.status_code == 200

    # password change upserts radcheck
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}",
        json={"email": "bob@netgrid.local", "password": "newpass456"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    password_rows = await _radcheck_rows(session, "bob", "Cleartext-Password")
    assert len(password_rows) == 1
    assert password_rows[0].value == "newpass456"

    # suspend adds the Reject row; reactivate removes it
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"status": "suspended"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert len(await _radcheck_rows(session, "bob", "Auth-Type")) == 1
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"status": "active"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert len(await _radcheck_rows(session, "bob", "Auth-Type")) == 0

    # delete removes profile + radcheck rows
    resp = await client.delete(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))
    assert resp.status_code == 204, resp.text
    assert (
        await session.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    ).scalar_one_or_none() is None
    assert await _radcheck_rows(session, "bob") == []


async def test_create_with_status_suspended(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={
            "username": "bob",
            "full_name": "Bob",
            "password": "radpass123",
            "status": "suspended",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    assert len(await _radcheck_rows(session, "bob", "Auth-Type")) == 1


async def test_duplicate_username_409(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    payload = {"username": "bob", "full_name": "Bob", "password": "radpass123"}
    assert (
        await client.post("/api/v1/subscribers", json=payload, headers=_auth(token))
    ).status_code == 201
    resp = await client.post("/api/v1/subscribers", json=payload, headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_invalid_status_422(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={
            "username": "bob",
            "full_name": "Bob",
            "password": "radpass123",
            "status": "banana",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_auditor_read_only(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob", "password": "radpass123"},
        headers=_auth(super_token),
    )
    subscriber_id = resp.json()["id"]

    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")
    for method, path in [
        ("get", "/api/v1/subscribers"),
        ("get", f"/api/v1/subscribers/{subscriber_id}"),
    ]:
        resp = await client.request(method, path, headers=_auth(token))
        assert resp.status_code == 200, (method, path, resp.text)

    for method, path, body in [
        (
            "post",
            "/api/v1/subscribers",
            {"username": "x", "full_name": "X", "password": "radpass123"},
        ),
        ("patch", f"/api/v1/subscribers/{subscriber_id}", {"status": "suspended"}),
        ("delete", f"/api/v1/subscribers/{subscriber_id}", None),
    ]:
        resp = await client.request(method, path, json=body, headers=_auth(token))
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_without_permission_denied(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "x", "full_name": "X", "password": "radpass123"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


async def test_404_unknown_subscriber(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.get("/api/v1/subscribers/999", headers=_auth(token))
    assert resp.status_code == 404
    # PATCH needs a body (even an empty one) or FastAPI 422s before the handler's 404
    resp = await client.patch("/api/v1/subscribers/999", json={}, headers=_auth(token))
    assert resp.status_code == 404
    resp = await client.delete("/api/v1/subscribers/999", headers=_auth(token))
    assert resp.status_code == 404


async def test_audit_entries_written(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob", "password": "radpass123"},
        headers=_auth(token),
    )
    subscriber_id = resp.json()["id"]
    await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"status": "suspended"}, headers=_auth(token)
    )
    await client.delete(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))

    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    actions = {(row.action, row.resource) for row in rows}
    assert ("create", "subscribers") in actions
    assert ("update", "subscribers") in actions
    assert ("delete", "subscribers") in actions
