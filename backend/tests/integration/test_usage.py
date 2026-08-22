"""Integration tests for the data-cap usage API (usage:read)."""

from datetime import timedelta
from decimal import Decimal

from app.core.security import hash_password
from app.models.plan import Plan
from app.models.radius import RadAcct
from app.models.rbac import Admin, Permission, Role
from app.models.subscriber import Subscriber
from app.services.usage import month_window, monthly_windows


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


def _seed_plan(session, name: str, quota_gb: int | None) -> Plan:
    plan = Plan(
        name=name,
        radius_group=f"grp-{name.lower()}",
        price=Decimal("9.99"),
        duration_days=30,
        bandwidth_down_mbps=100,
        bandwidth_up_mbps=10,
        quota_gb=quota_gb,
    )
    session.add(plan)
    return plan


def _seed_subscriber(session, plan: Plan, username: str) -> Subscriber:
    sub = Subscriber(
        username=username,
        full_name=f"{username} Smith",
        status="active",
        plan=plan,  # relationship so the FK resolves at flush
    )
    session.add(sub)
    return sub


def _seed_session(session, username: str, in_octets: int, out_octets: int) -> None:
    # deterministic in-window start: 12h into the current month (always inside
    # [month_start, month_end) regardless of when the suite runs)
    start = month_window()[0] + timedelta(hours=12)
    session.add(
        RadAcct(
            username=username,
            nasipaddress="192.168.0.10",
            acctstarttime=start,
            acctsessiontime=3600,
            acctinputoctets=in_octets,
            acctoutputoctets=out_octets,
            framedipaddress="10.0.0.5",
        )
    )


async def test_usage_report_lists_consumption_vs_quota(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = _seed_plan(session, "Starter", quota_gb=100)
    _seed_subscriber(session, plan, "demo-a1")
    _seed_subscriber(session, plan, "demo-a2")
    # 1 GiB down + 0.5 GiB up for demo-a1; nothing for demo-a2
    _seed_session(session, "demo-a1", 1024**3, 512 * 1024**2)
    await session.commit()

    resp = await client.get("/api/v1/usage", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["stats"]["over_quota_count"] == 0
    assert body["stats"]["total_consumed_gb"] == 1.5

    by_username = {item["username"]: item for item in body["items"]}
    assert by_username["demo-a1"]["total_gb"] == 1.5
    assert by_username["demo-a1"]["quota_gb"] == 100
    assert by_username["demo-a1"]["pct_used"] == 1.5
    assert by_username["demo-a1"]["plan_name"] == "Starter"
    # zero-usage subscriber still listed with its quota
    assert by_username["demo-a2"]["total_octets"] == 0
    assert by_username["demo-a2"]["total_gb"] == 0
    assert by_username["demo-a2"]["pct_used"] == 0


async def test_usage_report_counts_over_quota(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = _seed_plan(session, "Tiny", quota_gb=1)
    _seed_subscriber(session, plan, "heavy")
    # 2 GiB > 1 GiB quota
    _seed_session(session, "heavy", 2 * 1024**3, 0)
    await session.commit()

    resp = await client.get("/api/v1/usage", headers=_auth(token))
    body = resp.json()
    assert body["stats"]["over_quota_count"] == 1
    item = body["items"][0]
    assert item["pct_used"] == 200
    assert item["total_gb"] == 2


async def test_usage_report_unplanned_subscribers_excluded(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    _seed_subscriber(session, _seed_plan(session, "Starter", 100), "with-plan")
    session.add(Subscriber(username="no-plan", full_name="No Plan", status="active"))
    await session.commit()

    resp = await client.get("/api/v1/usage", headers=_auth(token))
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["username"] == "with-plan"


async def test_usage_report_ordered_by_username(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = _seed_plan(session, "Starter", 100)
    for username in ["zeta", "alpha", "mike"]:
        _seed_subscriber(session, plan, username)
    await session.commit()

    resp = await client.get("/api/v1/usage", headers=_auth(token))
    body = resp.json()
    assert [item["username"] for item in body["items"]] == ["alpha", "mike", "zeta"]


async def test_auditor_can_read_usage(client, session):
    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")
    _seed_subscriber(session, _seed_plan(session, "Starter", 100), "demo-a1")
    await session.commit()

    resp = await client.get("/api/v1/usage", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_usage_without_permission_403(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)

    resp = await client.get("/api/v1/usage", headers=_auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def _seed_session_in(session, username: str, in_octets: int, out_octets: int, start) -> None:
    session.add(
        RadAcct(
            username=username,
            nasipaddress="192.168.0.10",
            acctstarttime=start,
            acctsessiontime=3600,
            acctinputoctets=in_octets,
            acctoutputoctets=out_octets,
            framedipaddress="10.0.0.5",
        )
    )


async def test_subscriber_usage_history_endpoint(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = _seed_plan(session, "Starter", quota_gb=100)
    sub = _seed_subscriber(session, plan, "demo-a1")
    await session.commit()

    prev, current = monthly_windows(2)
    # 1 GiB this month + 2 GiB last month
    await _seed_session_in(session, "demo-a1", 1024**3, 0, current[0] + timedelta(hours=12))
    await _seed_session_in(session, "demo-a1", 2 * 1024**3, 0, prev[0] + timedelta(hours=6))
    await session.commit()

    resp = await client.get(f"/api/v1/subscribers/{sub.id}/usage", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 12  # default window
    assert body[-1]["month"] == current[0].strftime("%Y-%m")
    assert body[-1]["total_octets"] == 1024**3
    assert body[-1]["total_gb"] == 1.0
    assert body[-1]["session_count"] == 1
    assert body[-1]["quota_gb"] == 100
    assert body[-1]["pct_used"] == 1.0
    assert body[-2]["total_octets"] == 2 * 1024**3  # previous month
    assert body[-2]["pct_used"] == 2.0
    assert all("-" in m["month"] and len(m["month"]) == 7 for m in body)


async def test_subscriber_usage_history_months_param(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    plan = _seed_plan(session, "Starter", quota_gb=100)
    sub = _seed_subscriber(session, plan, "demo-a1")
    await session.commit()

    resp = await client.get(f"/api/v1/subscribers/{sub.id}/usage?months=2", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_subscriber_usage_history_unknown_subscriber_404(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.get("/api/v1/subscribers/999999/usage", headers=_auth(token))
    assert resp.status_code == 404


async def test_subscriber_usage_history_requires_subscribers_read(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)

    resp = await client.get("/api/v1/subscribers/1/usage", headers=_auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
