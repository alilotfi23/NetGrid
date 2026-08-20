from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.rbac import Admin, Permission, Role


async def _seed_admin(session, username="root", password="secret123", codes=("admins:read",)):
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password(password),
        is_active=True,
    )
    role = Role(name=f"role_{username}")
    role.permissions = [Permission(code=code) for code in codes]
    admin.roles.append(role)
    session.add(admin)
    await session.commit()
    return admin


async def _latest_audit(session) -> AuditLog | None:
    result = await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def _login(client, username="root"):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def test_login_success_is_audited(client, session):
    await _seed_admin(session)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    assert resp.status_code == 200
    entry = await _latest_audit(session)
    assert entry is not None
    assert entry.action == "login"
    assert entry.resource == "auth"
    assert entry.admin_id is not None
    assert entry.metadata_ and "ip" in entry.metadata_


async def test_login_failure_is_audited(client, session):
    await _seed_admin(session)
    resp = await client.post("/api/v1/auth/login", json={"username": "root", "password": "wrong"})
    assert resp.status_code == 401
    entry = await _latest_audit(session)
    assert entry is not None
    assert entry.action == "login_failed"
    assert entry.admin_id is None
    assert entry.metadata_ == {"username": "root", "ip": "127.0.0.1"}


async def test_permission_denied_is_audited(client, session):
    await _seed_admin(session, codes=("plans:read",))
    login = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    token = login.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    entry = await _latest_audit(session)
    assert entry is not None
    assert entry.action == "permission_denied"
    assert entry.resource == "rbac"
    assert entry.metadata_ == {"permission": "admins:read", "path": "/api/v1/auth/me"}


async def test_allowed_request_not_logged_as_denial(client, session):
    await _seed_admin(session, codes=("admins:read",))
    login = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    token = login.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    result = await session.execute(select(AuditLog).where(AuditLog.action == "permission_denied"))
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# Read side (Phase 12 audit log viewer)
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_audit_logs_read_requires_permission(client, session):
    """audit_logs:read gates the endpoint; denials are themselves audited."""
    await _seed_admin(session, "boss", codes=("*:*",))
    boss_token = await _login(client, "boss")

    resp = await client.get("/api/v1/audit-logs", headers=_auth(boss_token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1  # the login itself is in the trail

    await _seed_admin(session, "limited", codes=("plans:read",))
    token = await _login(client, "limited")
    resp = await client.get("/api/v1/audit-logs", headers=_auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    # the denial is recorded in the trail, attributed to the limited admin
    entry = await _latest_audit(session)
    assert entry is not None
    assert entry.action == "permission_denied"
    assert entry.resource == "rbac"
    assert entry.metadata_ == {"permission": "audit_logs:read", "path": "/api/v1/audit-logs"}


async def test_audit_logs_lists_filters_and_joins_username(client, session):
    """The list joins admin usernames, exposes filter options, and filters work."""
    await _seed_admin(session, "boss", codes=("*:*",))
    boss_token = await _login(client, "boss")  # audited as action=login, resource=auth
    boss_id = (await session.execute(select(Admin.id).where(Admin.username == "boss"))).scalar_one()

    resp = await client.post(
        "/api/v1/plans",
        json={
            "name": "Starter",
            "radius_group": "rad_starter",
            "price": "10.00",
            "duration_days": 30,
            "bandwidth_down_mbps": 10,
            "bandwidth_up_mbps": 5,
        },
        headers=_auth(boss_token),
    )
    assert resp.status_code == 201

    body = (await client.get("/api/v1/audit-logs", headers=_auth(boss_token))).json()
    assert body["total"] == 2
    assert [entry["action"] for entry in body["items"]] == ["create", "login"]
    assert body["items"][0]["admin_username"] == "boss"
    assert body["items"][0]["resource_id"] is not None
    assert body["items"][1]["admin_username"] == "boss"

    # filter options reflect the trail
    assert "login" in body["filters"]["actions"]
    assert "plans" in body["filters"]["resources"]
    assert {"id": boss_id, "username": "boss"} in body["filters"]["admins"]

    # filter by actor
    resp = await client.get(f"/api/v1/audit-logs?admin_id={boss_id}", headers=_auth(boss_token))
    assert resp.json()["total"] == 2
    # filter by action
    resp = await client.get("/api/v1/audit-logs?action=create", headers=_auth(boss_token))
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["resource"] == "plans"
    # filter by resource
    resp = await client.get("/api/v1/audit-logs?resource=auth", headers=_auth(boss_token))
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["action"] == "login"
    # pagination
    body = (await client.get("/api/v1/audit-logs?page_size=1", headers=_auth(boss_token))).json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["page"] == 1
    assert body["page_size"] == 1
    # invalid actor id is rejected by validation
    resp = await client.get("/api/v1/audit-logs?admin_id=abc", headers=_auth(boss_token))
    assert resp.status_code == 422
