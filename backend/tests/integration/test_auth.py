from app.core.security import hash_password
from app.models.rbac import Admin


async def _seed_admin(session, username="root", password="secret123") -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password(password),
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    return admin


async def test_login_success(client, session):
    await _seed_admin(session)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["admin"]["username"] == "root"


async def test_login_invalid_credentials(client, session):
    await _seed_admin(session)
    resp = await client.post("/api/v1/auth/login", json={"username": "root", "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_login_validation_error(client):
    resp = await client.post("/api/v1/auth/login", json={"username": ""})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_me_requires_token(client, session):
    await _seed_admin(session)
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_with_token(client, session):
    admin = await _seed_admin(session)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    token = login.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == admin.id
    assert body["username"] == "root"


async def test_refresh_flow_rotates(client, session):
    await _seed_admin(session)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    old_refresh = login.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new = resp.json()
    assert new["access_token"]
    assert new["refresh_token"] != old_refresh  # rotation
    # the rotated-away token must no longer work
    resp2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


async def test_logout_revokes_refresh(client, session):
    await _seed_admin(session)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 204
    resp2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


async def test_refresh_rejects_access_token(client, session):
    await _seed_admin(session)
    login = await client.post(
        "/api/v1/auth/login", json={"username": "root", "password": "secret123"}
    )
    access_token = login.json()["access_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
