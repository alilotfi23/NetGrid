"""Integration tests for the plans API + RADIUS group coupling (Phase 6)."""

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.radius import RadGroupReply, RadUserGroup
from app.models.rbac import Admin, Permission, Role
from app.models.subscriber import Subscriber


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


async def _create_plan_via_api(client, token, name="Starter", radius_group="rad_starter"):
    resp = await client.post(
        "/api/v1/plans",
        json=_plan_payload(name=name, radius_group=radius_group),
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _plan_payload(name="Starter", radius_group="rad_starter", **overrides):
    payload = {
        "name": name,
        "radius_group": radius_group,
        "price": "9.99",
        "duration_days": 30,
        "bandwidth_down_mbps": 10,
        "bandwidth_up_mbps": 5,
        "quota_gb": 100,
    }
    payload.update(overrides)
    return payload


async def _reply_rows(session, group: str, attribute: str | None = None) -> list[RadGroupReply]:
    stmt = select(RadGroupReply).where(RadGroupReply.groupname == group)
    if attribute is not None:
        stmt = stmt.where(RadGroupReply.attribute == attribute)
    return list((await session.execute(stmt)).scalars().all())


async def test_superadmin_full_lifecycle(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.post("/api/v1/plans", json=_plan_payload(), headers=_auth(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    plan_id = body["id"]
    assert body["name"] == "Starter"
    assert body["radius_group"] == "rad_starter"
    assert body["price"] == "9.99"

    # the plan's RADIUS group carries the attribute replies
    rows = await _reply_rows(session, "rad_starter")
    assert {r.attribute for r in rows} == {
        "WISPr-Bandwidth-Max-Down",
        "WISPr-Bandwidth-Max-Up",
        "Mikrotik-Total-Limit",
        "Mikrotik-Total-Limit-Gigawords",
    }
    # 100 GB quota as the 64-bit pair (low 32 bits / gigawords)
    assert {r.value for r in rows} == {"10000", "5000", "1215752192", "23"}

    resp = await client.get("/api/v1/plans", headers=_auth(token))
    assert resp.status_code == 200
    assert "Starter" in [p["name"] for p in resp.json()["items"]]

    resp = await client.get(f"/api/v1/plans/{plan_id}", headers=_auth(token))
    assert resp.status_code == 200

    # bandwidth change re-syncs the group rows (no duplicates)
    resp = await client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"bandwidth_down_mbps": 20, "is_active": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["bandwidth_down_mbps"] == 20
    down = await _reply_rows(session, "rad_starter", "WISPr-Bandwidth-Max-Down")
    assert len(down) == 1
    assert down[0].value == "20000"


async def test_plan_assignment_writes_radusergroup(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan_id = (await _create_plan_via_api(client, token))["id"]

    resp = await client.post(
        "/api/v1/subscribers",
        json={
            "username": "bob",
            "full_name": "Bob",
            "password": "radpass123",
            "plan_id": plan_id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    subscriber_id = resp.json()["id"]
    assert resp.json()["plan_id"] == plan_id

    memberships = (
        (await session.execute(select(RadUserGroup).where(RadUserGroup.username == "bob")))
        .scalars()
        .all()
    )
    assert [(m.groupname, m.priority) for m in memberships] == [("rad_starter", 1)]

    # switch plan -> membership replaced
    other = await _create_plan_via_api(client, token, name="Pro", radius_group="rad_pro")
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"plan_id": other["id"]}, headers=_auth(token)
    )
    assert resp.status_code == 200
    memberships = (
        (await session.execute(select(RadUserGroup).where(RadUserGroup.username == "bob")))
        .scalars()
        .all()
    )
    assert [m.groupname for m in memberships] == ["rad_pro"]

    # clear plan -> membership removed
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"plan_id": None}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["plan_id"] is None
    remaining = (
        (await session.execute(select(RadUserGroup).where(RadUserGroup.username == "bob")))
        .scalars()
        .all()
    )
    assert remaining == []


async def test_subscriber_delete_removes_radusergroup(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan_id = (await _create_plan_via_api(client, token))["id"]
    subscriber_id = (
        await client.post(
            "/api/v1/subscribers",
            json={
                "username": "bob",
                "full_name": "Bob",
                "password": "radpass123",
                "plan_id": plan_id,
            },
            headers=_auth(token),
        )
    ).json()["id"]

    resp = await client.delete(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))
    assert resp.status_code == 204
    assert (
        await session.execute(select(RadUserGroup).where(RadUserGroup.username == "bob"))
    ).scalars().all() == []
    assert (
        await session.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    ).scalar_one_or_none() is None


async def test_duplicate_name_and_group_409(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    assert (
        await client.post("/api/v1/plans", json=_plan_payload(), headers=_auth(token))
    ).status_code == 201
    resp = await client.post("/api/v1/plans", json=_plan_payload(), headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
    resp = await client.post(
        "/api/v1/plans",
        json=_plan_payload(name="Other", radius_group="rad_starter"),
        headers=_auth(token),
    )
    assert resp.status_code == 409


async def test_invalid_payload_422(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/plans",
        json=_plan_payload(bandwidth_down_mbps=-1),
        headers=_auth(token),
    )
    assert resp.status_code == 422
    # name is immutable on update: it is absent from PlanUpdate, so a PATCH
    # carrying it is a no-op that leaves the plan unchanged
    plan_id = (await _create_plan_via_api(client, token))["id"]
    resp = await client.patch(
        f"/api/v1/plans/{plan_id}", json={"name": "Renamed"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Starter"


async def test_auditor_read_only(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    plan_id = (await _create_plan_via_api(client, super_token))["id"]

    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")
    for method, path in [
        ("get", "/api/v1/plans"),
        ("get", f"/api/v1/plans/{plan_id}"),
    ]:
        resp = await client.request(method, path, headers=_auth(token))
        assert resp.status_code == 200, (method, path, resp.text)

    for method, path, body in [
        ("post", "/api/v1/plans", _plan_payload(name="X", radius_group="rad_x")),
        ("patch", f"/api/v1/plans/{plan_id}", {"is_active": False}),
    ]:
        resp = await client.request(method, path, json=body, headers=_auth(token))
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_without_permission_denied(client, session):
    await _seed_admin(session, "boss", ["subscribers:read"])
    token = await _login(client)
    resp = await client.post("/api/v1/plans", json=_plan_payload(), headers=_auth(token))
    assert resp.status_code == 403


async def test_404_unknown_plan(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.get("/api/v1/plans/999", headers=_auth(token))
    assert resp.status_code == 404
    resp = await client.patch("/api/v1/plans/999", json={"is_active": False}, headers=_auth(token))
    assert resp.status_code == 404


async def test_audit_entries_written(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan_id = (await _create_plan_via_api(client, token))["id"]
    await client.patch(f"/api/v1/plans/{plan_id}", json={"price": "12.50"}, headers=_auth(token))
    rows = (await session.execute(select(AuditLog))).scalars().all()
    actions = {(row.action, row.resource) for row in rows}
    assert ("create", "plans") in actions
    assert ("update", "plans") in actions
    # the Decimal round-trips through the API
    update = next(r for r in rows if r.action == "update" and r.resource == "plans")
    assert update.metadata_ == {"name": "Starter", "fields": ["price"]}
