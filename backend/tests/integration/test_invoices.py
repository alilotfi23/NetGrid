"""Integration tests for the invoices API + payment flows (Phase 10)."""

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.billing import Invoice
from app.models.rbac import Admin


async def _seed_admin(session, username, codes) -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    from app.models.rbac import Permission, Role

    role_obj = Role(name=f"role_{username}")
    role_obj.permissions = [Permission(code=code) for code in codes]
    admin.roles.append(role_obj)
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


async def _create_plan(client, token, name="Starter"):
    resp = await client.post(
        "/api/v1/plans",
        json={
            "name": name,
            "radius_group": f"rad_{name.lower()}",
            "price": "10.00",
            "duration_days": 30,
            "bandwidth_down_mbps": 10,
            "bandwidth_up_mbps": 5,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_subscriber(client, token, username, plan_id):
    resp = await client.post(
        "/api/v1/subscribers",
        json={
            "username": username,
            "full_name": username,
            "password": "radpass123",
            "plan_id": plan_id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _generate(client, token, **overrides):
    payload = {"period_start": "2026-03-01", "period_end": "2026-03-30"}
    payload.update(overrides)
    resp = await client.post("/api/v1/invoices/generate", json=payload, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_superadmin_full_lifecycle(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token)
    sub = await _create_subscriber(client, token, "bob", plan["id"])

    # generate for a fixed past period so proration doesn't kick in
    result = await _generate(client, token)
    assert result["created"] == 1

    # list shows the invoice with stats and the subscriber's username
    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["stats"]["issued"] == 1
    assert body["items"][0]["subscriber_username"] == "bob"
    assert body["items"][0]["plan_name"] == "Starter"
    invoice_id = body["items"][0]["id"]

    # detail includes the (empty) payments list
    resp = await client.get(f"/api/v1/invoices/{invoice_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["payments"] == []
    assert resp.json()["subscriber_username"] == "bob"

    # filter by subscriber
    resp = await client.get(f"/api/v1/invoices?subscriber_id={sub['id']}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # full payment -> paid
    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": "10.00", "method": "cash"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["payment"]["status"] == "completed"
    assert body["invoice"]["status"] == "paid"
    assert body["invoice"]["paid_at"] is not None

    # stats now show one paid invoice, nothing outstanding
    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    assert resp.json()["stats"]["paid"] == 1
    assert resp.json()["stats"]["outstanding_amount"] == "0.00"


async def test_generate_is_idempotent(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token)
    await _create_subscriber(client, token, "bob", plan["id"])

    assert (await _generate(client, token))["created"] == 1
    assert (await _generate(client, token))["created"] == 0

    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    assert resp.json()["total"] == 1


async def test_partial_payments_then_full(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token)
    await _create_subscriber(client, token, "bob", plan["id"])
    await _generate(client, token)
    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    invoice_id = resp.json()["items"][0]["id"]

    # partial payment keeps it issued
    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": "6.00", "method": "bank_transfer", "reference": "TXN-1"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["invoice"]["status"] == "issued"

    # remainder completes it
    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": "4.00", "method": "bank_transfer", "reference": "TXN-2"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["invoice"]["status"] == "paid"

    # the detail view lists both payments
    resp = await client.get(f"/api/v1/invoices/{invoice_id}", headers=_auth(token))
    assert len(resp.json()["payments"]) == 2
    assert [p["reference"] for p in resp.json()["payments"]] == ["TXN-1", "TXN-2"]


async def test_paying_paid_invoice_conflicts(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token)
    await _create_subscriber(client, token, "bob", plan["id"])
    await _generate(client, token)
    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    invoice_id = resp.json()["items"][0]["id"]

    await client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": "10.00", "method": "cash"},
        headers=_auth(token),
    )
    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": "1.00", "method": "cash"},
        headers=_auth(token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_invalid_payloads_422(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    # negative payment amount
    resp = await client.post(
        "/api/v1/invoices/1/payments",
        json={"amount": "-5.00", "method": "cash"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
    # inverted period
    resp = await client.post(
        "/api/v1/invoices/generate",
        json={"period_start": "2026-03-30", "period_end": "2026-03-01"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"


async def test_404_unknown_invoice(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.get("/api/v1/invoices/999", headers=_auth(token))
    assert resp.status_code == 404
    resp = await client.post(
        "/api/v1/invoices/999/payments",
        json={"amount": "5.00", "method": "cash"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


async def test_auditor_read_only(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    plan = await _create_plan(client, super_token)
    await _create_subscriber(client, super_token, "bob", plan["id"])
    await _generate(client, super_token)
    invoice_id = (await client.get("/api/v1/invoices", headers=_auth(super_token))).json()["items"][
        0
    ]["id"]

    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")
    for method, path in [
        ("get", "/api/v1/invoices"),
        ("get", f"/api/v1/invoices/{invoice_id}"),
    ]:
        resp = await client.request(method, path, headers=_auth(token))
        assert resp.status_code == 200, (method, path, resp.text)

    for method, path, body in [
        ("post", "/api/v1/invoices/generate", {}),
        ("post", f"/api/v1/invoices/{invoice_id}/payments", {"amount": "5.00", "method": "cash"}),
    ]:
        resp = await client.request(method, path, json=body, headers=_auth(token))
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_without_permission_denied(client, session):
    await _seed_admin(session, "boss", ["subscribers:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    assert resp.status_code == 403
    resp = await client.post("/api/v1/invoices/generate", json={}, headers=_auth(token))
    assert resp.status_code == 403


async def test_audit_entries_written(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token)
    await _create_subscriber(client, token, "bob", plan["id"])
    await _generate(client, token)
    resp = await client.get("/api/v1/invoices", headers=_auth(token))
    invoice_id = resp.json()["items"][0]["id"]
    await client.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={"amount": "10.00", "method": "cash"},
        headers=_auth(token),
    )

    rows = (await session.execute(select(AuditLog))).scalars().all()
    actions = {(e.action, e.resource) for e in rows}
    assert ("generate", "invoices") in actions
    assert ("payment", "invoices") in actions
    generate = next(e for e in rows if e.action == "generate")
    assert generate.metadata_["created"] == 1


async def test_status_filter_validated(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.get("/api/v1/invoices?status=bogus", headers=_auth(token))
    assert resp.status_code == 422


async def test_scheduled_job_via_api_uses_default_period(client, session):
    """The API's generate endpoint mirrors the scheduler's default (this month)."""
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = await _create_plan(client, token)
    await _create_subscriber(client, token, "bob", plan["id"])

    resp = await client.post("/api/v1/invoices/generate", json={}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["created"] == 1

    from datetime import date

    invoices = (await session.execute(select(Invoice))).scalars().all()
    assert len(invoices) == 1
    assert invoices[0].period_start == date.today().replace(day=1)
    # overdue pass ran too, but a same-month invoice is never overdue
    assert invoices[0].status == "issued"
