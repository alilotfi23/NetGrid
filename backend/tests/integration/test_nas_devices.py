"""Integration tests for the NAS devices API (Phase 7)."""

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.radius import Nas
from app.models.rbac import Admin, Permission, Role


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


async def _login(client, username="boss"):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload(name="core-r1", ip_address="192.168.0.10", **overrides):
    payload = {
        "name": name,
        "ip_address": ip_address,
        "shortname": "core1",
        "nas_type": "other",
        "secret": "radius_secret_1",
        "ports": 1812,
        "server": "radius.internal",
        "community": "public",
        "description": "Core router",
    }
    payload.update(overrides)
    return payload


async def _create_via_api(client, token, **overrides):
    resp = await client.post(
        "/api/v1/nas-devices", json=_payload(**overrides), headers=_auth(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _nas_rows(session) -> list[Nas]:
    return list((await session.execute(select(Nas))).scalars().all())


async def test_superadmin_full_lifecycle(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    # create -> inventory row + FreeRADIUS nas row with the plaintext secret
    resp = await client.post("/api/v1/nas-devices", json=_payload(), headers=_auth(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    device_id = body["id"]
    assert body["name"] == "core-r1"
    assert body["ip_address"] == "192.168.0.10"
    assert "secret" not in body  # the shared secret is never returned

    rows = await _nas_rows(session)
    assert len(rows) == 1
    assert rows[0].nasname == "192.168.0.10"
    assert rows[0].secret == "radius_secret_1"

    resp = await client.get("/api/v1/nas-devices", headers=_auth(token))
    assert resp.status_code == 200
    assert "core-r1" in [d["name"] for d in resp.json()["items"]]

    resp = await client.get(f"/api/v1/nas-devices/{device_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert "secret" not in resp.json()

    # rotate the secret via the dedicated action -> nas row carries the new
    # plaintext without any other field being touched
    resp = await client.post(
        f"/api/v1/nas-devices/{device_id}/rotate-secret",
        json={"secret": "rotated_secret_9"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "secret" not in resp.json()
    assert resp.json()["name"] == "core-r1"  # other fields untouched
    rows = await _nas_rows(session)
    assert len(rows) == 1
    assert rows[0].secret == "rotated_secret_9"

    # deactivate -> nas row removed (FreeRADIUS sees an unknown NAS)
    resp = await client.patch(
        f"/api/v1/nas-devices/{device_id}", json={"is_active": False}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert await _nas_rows(session) == []

    # reactivate -> nas row recreated with the current (rotated) secret
    resp = await client.patch(
        f"/api/v1/nas-devices/{device_id}", json={"is_active": True}, headers=_auth(token)
    )
    assert resp.status_code == 200
    rows = await _nas_rows(session)
    assert len(rows) == 1
    assert rows[0].secret == "rotated_secret_9"

    # delete -> both rows gone
    resp = await client.delete(f"/api/v1/nas-devices/{device_id}", headers=_auth(token))
    assert resp.status_code == 204
    assert await _nas_rows(session) == []


async def test_duplicate_name_and_ip_409(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    assert (
        await client.post("/api/v1/nas-devices", json=_payload(), headers=_auth(token))
    ).status_code == 201
    resp = await client.post("/api/v1/nas-devices", json=_payload(), headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
    resp = await client.post(
        "/api/v1/nas-devices",
        json=_payload(name="edge-1", ip_address="192.168.0.10"),
        headers=_auth(token),
    )
    assert resp.status_code == 409


async def test_invalid_payload_422(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    for overrides in [
        {"ports": 0},  # out of range
        {"secret": ""},  # empty secret
        {"secret": "x" * 64},  # over the RADIUS 63-char limit
        {"ip_address": "has space"},  # whitespace in the RADIUS identity
    ]:
        resp = await client.post(
            "/api/v1/nas-devices", json=_payload(**overrides), headers=_auth(token)
        )
        assert resp.status_code == 422, (overrides, resp.text)


async def test_ip_address_immutable_on_update(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    device = await _create_via_api(client, token)
    # unknown fields are ignored by Pydantic, so a PATCH carrying ip_address
    # is a no-op that leaves the RADIUS identity untouched
    resp = await client.patch(
        f"/api/v1/nas-devices/{device['id']}",
        json={"ip_address": "10.9.9.9"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["ip_address"] == "192.168.0.10"
    rows = await _nas_rows(session)
    assert rows[0].nasname == "192.168.0.10"


async def test_auditor_read_only(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    device = await _create_via_api(client, super_token)

    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")
    for method, path in [
        ("get", "/api/v1/nas-devices"),
        ("get", f"/api/v1/nas-devices/{device['id']}"),
    ]:
        resp = await client.request(method, path, headers=_auth(token))
        assert resp.status_code == 200, (method, path, resp.text)

    for method, path, body in [
        ("post", "/api/v1/nas-devices", _payload(name="x", ip_address="10.1.1.1")),
        ("patch", f"/api/v1/nas-devices/{device['id']}", {"is_active": False}),
        ("post", f"/api/v1/nas-devices/{device['id']}/rotate-secret", {"secret": "x"}),
        ("delete", f"/api/v1/nas-devices/{device['id']}", None),
    ]:
        resp = await client.request(method, path, json=body, headers=_auth(token))
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_without_permission_denied(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)
    resp = await client.post("/api/v1/nas-devices", json=_payload(), headers=_auth(token))
    assert resp.status_code == 403


async def test_404_unknown_device(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.get("/api/v1/nas-devices/999", headers=_auth(token))
    assert resp.status_code == 404
    resp = await client.patch(
        "/api/v1/nas-devices/999", json={"is_active": False}, headers=_auth(token)
    )
    assert resp.status_code == 404
    resp = await client.delete("/api/v1/nas-devices/999", headers=_auth(token))
    assert resp.status_code == 404


async def test_audit_entries_written(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    device = await _create_via_api(client, token)
    await client.post(
        f"/api/v1/nas-devices/{device['id']}/rotate-secret",
        json={"secret": "rotated_1"},
        headers=_auth(token),
    )
    await client.delete(f"/api/v1/nas-devices/{device['id']}", headers=_auth(token))

    rows = (await session.execute(select(AuditLog))).scalars().all()
    actions = {(row.action, row.resource) for row in rows}
    assert ("create", "nas_devices") in actions
    assert ("rotate_secret", "nas_devices") in actions
    assert ("delete", "nas_devices") in actions


async def test_rotate_secret_validation(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    device = await _create_via_api(client, token)

    # empty and over-long secrets are rejected without touching the stored one
    for bad in ["", "x" * 64]:
        resp = await client.post(
            f"/api/v1/nas-devices/{device['id']}/rotate-secret",
            json={"secret": bad},
            headers=_auth(token),
        )
        assert resp.status_code == 422, (bad, resp.text)
    rows = await _nas_rows(session)
    assert rows[0].secret == "radius_secret_1"

    resp = await client.post(
        "/api/v1/nas-devices/999/rotate-secret", json={"secret": "x"}, headers=_auth(token)
    )
    assert resp.status_code == 404
