"""Integration tests for the plan-level enforce_quota toggle (API surface)."""

from app.core.security import hash_password
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


def _payload(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Starter",
        "radius_group": "rad_starter",
        "price": "9.99",
        "duration_days": 30,
        "bandwidth_down_mbps": 10,
        "bandwidth_up_mbps": 5,
        "quota_gb": 100,
    }
    payload.update(overrides)
    return payload


async def test_plan_create_defaults_enforcement_off(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.post("/api/v1/plans", json=_payload(), headers=_auth(token))
    assert resp.status_code == 201, resp.text
    # opt-in: a plan never enforces until the operator flips the toggle
    assert resp.json()["enforce_quota"] is False


async def test_plan_enforce_quota_round_trip_via_api(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    created = await client.post(
        "/api/v1/plans", json=_payload(enforce_quota=True), headers=_auth(token)
    )
    assert created.status_code == 201, created.text
    assert created.json()["enforce_quota"] is True

    plan_id = created.json()["id"]
    patched = await client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"enforce_quota": False},
        headers=_auth(token),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["enforce_quota"] is False


async def test_plan_update_ignores_unset_toggle(client, session):
    """A PATCH without enforce_quota must not flip the flag."""
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    created = await client.post(
        "/api/v1/plans", json=_payload(enforce_quota=True), headers=_auth(token)
    )
    plan_id = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"price": "12.50"},
        headers=_auth(token),
    )
    assert patched.status_code == 200
    assert patched.json()["enforce_quota"] is True
