"""Integration tests for usage overage billing (plan rate + API trigger)."""

from datetime import UTC, datetime

from app.core.security import hash_password
from app.models.radius import RadAcct
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


async def _create_plan(client, token, **overrides) -> dict[str, object]:
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
    resp = await client.post("/api/v1/plans", json=payload, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_subscriber(client, token, plan_id: int) -> dict[str, object]:
    resp = await client.post(
        "/api/v1/subscribers",
        json={
            "username": "heavy",
            "full_name": "Heavy User",
            "password": "secret123",
            "status": "active",
            "plan_id": plan_id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_usage(session, username: str) -> None:
    """150 GiB of July 2026 usage — 50 GB over a 100 GB quota."""
    session.add(
        RadAcct(
            username=username,
            nasipaddress="192.168.0.10",
            acctstarttime=datetime(2026, 7, 15, tzinfo=UTC),
            acctsessiontime=3600,
            acctinputoctets=150 * 1024**3,
            acctoutputoctets=0,
            framedipaddress="10.0.0.5",
        )
    )


async def test_plan_overage_price_round_trip_via_api(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    created = await _create_plan(client, token, overage_price_per_gb="0.50")
    plan_id = created["id"]
    assert created["overage_price_per_gb"] == "0.50"

    patched = await client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"overage_price_per_gb": "1.25"},
        headers=_auth(token),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["overage_price_per_gb"] == "1.25"


async def test_overage_generate_endpoint_bills_excess_usage(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token, overage_price_per_gb="0.50")
    sub = await _create_subscriber(client, token, plan["id"])  # type: ignore[arg-type]
    _seed_usage(session, "heavy")
    await session.commit()

    resp = await client.post(
        "/api/v1/invoices/overage/generate",
        json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1

    listed = await client.get(
        f"/api/v1/invoices?subscriber_id={sub['id']}", headers=_auth(token)
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "overage"
    assert items[0]["amount"] == "25.00"  # 50 GB over at $0.50
    assert items[0]["plan_name"] == "Starter"

    # idempotent: a second run bills nothing new
    again = await client.post(
        "/api/v1/invoices/overage/generate",
        json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
        headers=_auth(token),
    )
    assert again.json()["created"] == 0


async def test_overage_generate_requires_invoices_write(client, session):
    await _seed_admin(session, "boss", ["invoices:read"])
    token = await _login(client)

    resp = await client.post(
        "/api/v1/invoices/overage/generate",
        json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
        headers=_auth(token),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_overage_invoice_flows_through_base_generate_too(client, session):
    """The base generate endpoint keeps working with overage rows present."""
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token, overage_price_per_gb="0.50")
    await _create_subscriber(client, token, plan["id"])  # type: ignore[arg-type]
    _seed_usage(session, "heavy")
    await session.commit()

    overage = await client.post(
        "/api/v1/invoices/overage/generate",
        json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
        headers=_auth(token),
    )
    assert overage.json()["created"] == 1

    base = await client.post(
        "/api/v1/invoices/generate",
        json={"period_start": "2026-07-01", "period_end": "2026-07-31"},
        headers=_auth(token),
    )
    assert base.status_code == 200, base.text
    assert base.json()["created"] == 1  # kinds are separate, no double-billing block
