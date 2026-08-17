from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.rbac import Admin, Permission, Role


async def _ensure_permissions(session, *codes: str) -> None:
    """Create permission rows the catalog validation requires."""
    existing = set((await session.execute(select(Permission.code))).scalars().all())
    for code in codes:
        if code not in existing:
            session.add(Permission(code=code))
    await session.commit()


async def _seed_admin(session, username, codes) -> Admin:
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


async def _seed_role(session, name="support", codes=None) -> Role:
    role = Role(name=name)
    role.permissions = [Permission(code=code) for code in codes or []]
    session.add(role)
    await session.commit()
    return role


async def _seed_admin_with_role(session, username, role) -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
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


async def test_superadmin_full_lifecycle(client, session):
    await _ensure_permissions(session, "subscribers:read")
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.post(
        "/api/v1/roles",
        json={"name": "support", "permission_codes": ["subscribers:read"]},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    role_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/admins",
        json={
            "username": "bob",
            "email": "bob@netgrid.local",
            "password": "secret123",
            "role_ids": [role_id],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    admin_id = resp.json()["id"]
    assert [r["id"] for r in resp.json()["roles"]] == [role_id]

    # the created admin can log in; subscribers:read does not grant /me
    bob_token = await _login(client, "bob")
    resp = await client.get("/api/v1/auth/me", headers=_auth(bob_token))
    assert resp.status_code == 403

    resp = await client.get("/api/v1/admins", headers=_auth(token))
    assert resp.status_code == 200
    assert "bob" in [a["username"] for a in resp.json()["items"]]

    resp = await client.put(
        f"/api/v1/admins/{admin_id}/roles", json={"role_ids": []}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["roles"] == []

    resp = await client.patch(
        f"/api/v1/admins/{admin_id}",
        json={"email": "bob2@netgrid.local", "is_active": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "bob2@netgrid.local"
    assert resp.json()["is_active"] is False

    resp = await client.get("/api/v1/permissions", headers=_auth(token))
    assert resp.status_code == 200
    assert "subscribers:read" in {p["code"] for p in resp.json()["items"]}


async def test_auditor_read_only(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    resp = await client.post(
        "/api/v1/roles",
        json={"name": "support", "permission_codes": []},
        headers=_auth(super_token),
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/admins",
        json={"username": "bob", "email": "bob@netgrid.local", "password": "secret123"},
        headers=_auth(super_token),
    )
    admin_id = resp.json()["id"]

    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")

    for method, path in [
        ("get", "/api/v1/admins"),
        ("get", "/api/v1/roles"),
        ("get", "/api/v1/permissions"),
    ]:
        resp = await client.request(method, path, headers=_auth(token))
        assert resp.status_code == 200, (method, path, resp.text)

    mutations = [
        (
            "post",
            "/api/v1/admins",
            {"username": "x", "email": "x@netgrid.local", "password": "secret123"},
        ),
        ("post", "/api/v1/roles", {"name": "x", "permission_codes": []}),
        ("patch", f"/api/v1/admins/{admin_id}", {"is_active": False}),
        ("put", f"/api/v1/admins/{admin_id}/roles", {"role_ids": []}),
        ("put", f"/api/v1/roles/{role_id}/permissions", {"permission_codes": []}),
    ]
    for method, path, body in mutations:
        resp = await client.request(method, path, json=body, headers=_auth(token))
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_without_permission_denied(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/admins",
        json={"username": "x", "email": "x@netgrid.local", "password": "secret123"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


async def test_duplicate_username_409(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    payload = {"username": "bob", "email": "bob@netgrid.local", "password": "secret123"}
    assert (
        await client.post("/api/v1/admins", json=payload, headers=_auth(token))
    ).status_code == 201
    resp = await client.post("/api/v1/admins", json=payload, headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_patch_self_deactivate_400(client, session):
    admin = await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.patch(
        f"/api/v1/admins/{admin.id}", json={"is_active": False}, headers=_auth(token)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


async def test_put_own_roles_400(client, session):
    admin = await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.put(
        f"/api/v1/admins/{admin.id}/roles", json={"role_ids": []}, headers=_auth(token)
    )
    assert resp.status_code == 400


async def test_strip_own_manage_via_role_permissions_400(client, session):
    await _ensure_permissions(session, "subscribers:read")
    admin = await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    role_id = admin.roles[0].id
    resp = await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"permission_codes": ["subscribers:read"]},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


async def test_role_permission_change_revokes_old_tokens(client, session):
    await _ensure_permissions(session, "plans:read")
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    role = await _seed_role(session, "support", ["admins:read"])
    await _seed_admin_with_role(session, "alice", role)
    alice_token = await _login(client, "alice")
    resp = await client.get("/api/v1/auth/me", headers=_auth(alice_token))
    assert resp.status_code == 200

    resp = await client.put(
        f"/api/v1/roles/{role.id}/permissions",
        json={"permission_codes": ["plans:read"]},
        headers=_auth(super_token),
    )
    assert resp.status_code == 200

    # the pre-change token is stale: version mismatch -> 401
    resp = await client.get("/api/v1/auth/me", headers=_auth(alice_token))
    assert resp.status_code == 401

    # a fresh login carries the new version -> the check is a plain 403
    alice_token = await _login(client, "alice")
    resp = await client.get("/api/v1/auth/me", headers=_auth(alice_token))
    assert resp.status_code == 403


async def test_role_assignment_change_revokes_old_tokens(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    r1 = await _seed_role(session, "readonly", ["admins:read"])
    r2 = await _seed_role(session, "other", ["plans:read"])
    alice = await _seed_admin_with_role(session, "alice", r1)
    alice_token = await _login(client, "alice")
    assert (await client.get("/api/v1/auth/me", headers=_auth(alice_token))).status_code == 200

    resp = await client.put(
        f"/api/v1/admins/{alice.id}/roles", json={"role_ids": [r2.id]}, headers=_auth(super_token)
    )
    assert resp.status_code == 200

    resp = await client.get("/api/v1/auth/me", headers=_auth(alice_token))
    assert resp.status_code == 401

    alice_token = await _login(client, "alice")
    resp = await client.get("/api/v1/auth/me", headers=_auth(alice_token))
    assert resp.status_code == 403


async def test_404_unknown_resources(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.patch("/api/v1/admins/999", json={"email": "x@y.z"}, headers=_auth(token))
    assert resp.status_code == 404
    resp = await client.put(
        "/api/v1/roles/999/permissions", json={"permission_codes": []}, headers=_auth(token)
    )
    assert resp.status_code == 404
    resp = await client.post(
        "/api/v1/admins",
        json={
            "username": "bob",
            "email": "bob@netgrid.local",
            "password": "secret123",
            "role_ids": [999],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 404


async def test_audit_entries_written(client, session):
    await _ensure_permissions(session, "subscribers:read")
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/roles", json={"name": "support", "permission_codes": []}, headers=_auth(token)
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/admins",
        json={"username": "bob", "email": "bob@netgrid.local", "password": "secret123"},
        headers=_auth(token),
    )
    admin_id = resp.json()["id"]
    await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"permission_codes": ["subscribers:read"]},
        headers=_auth(token),
    )
    await client.put(
        f"/api/v1/admins/{admin_id}/roles", json={"role_ids": [role_id]}, headers=_auth(token)
    )

    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    actions = {(row.action, row.resource) for row in rows}
    assert ("create", "admins") in actions
    assert ("create", "roles") in actions
    assert ("update_permissions", "roles") in actions
    assert ("assign_roles", "admins") in actions
