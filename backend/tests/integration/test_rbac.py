from sqlalchemy import select

from app.core.security import hash_password
from app.models.rbac import Admin, Permission, Role
from app.services.rbac import invalidate_admin_permissions


async def _seed_admin_with_permissions(session, codes, username="boss") -> Admin:
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


async def _login(client, username="boss", password="secret123"):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _get_boss(session) -> Admin:
    return (await session.execute(select(Admin).where(Admin.username == "boss"))).scalar_one()


async def test_me_allowed_with_permission(client, session):
    await _seed_admin_with_permissions(session, ["admins:read", "plans:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "boss"


async def test_me_denied_without_permission(client, session):
    await _seed_admin_with_permissions(session, ["plans:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_me_auditor_wildcard_read(client, session):
    # auditor-style role: *:read matches admins:read via the wildcard
    await _seed_admin_with_permissions(session, ["*:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_revocation_rejects_stale_token(client, session):
    await _seed_admin_with_permissions(session, ["admins:read"])
    token = await _login(client)
    # revoke: strip the role's permissions and drop the cache
    admin = await _get_boss(session)
    admin.roles[0].permissions.clear()
    await session.commit()
    await invalidate_admin_permissions(admin.id)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_revocation_denies_after_relogin(client, session):
    await _seed_admin_with_permissions(session, ["admins:read"])
    await _login(client)  # burn a pre-revocation token so its version is stale
    admin = await _get_boss(session)
    admin.roles[0].permissions.clear()
    await session.commit()
    await invalidate_admin_permissions(admin.id)
    # a fresh login gets a token with the new perm_version — then the check is a 403
    new_token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
