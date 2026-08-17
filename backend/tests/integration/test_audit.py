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
