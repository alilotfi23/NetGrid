"""Integration tests for the live-sessions API (Phase 9 read side)."""

from datetime import UTC, datetime, timedelta

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


def _seed_sessions(session) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            RadAcct(
                username="bob",
                nasipaddress="192.168.0.10",
                acctstarttime=now - timedelta(minutes=30),
                acctsessiontime=1800,
                acctinputoctets=1024,
                acctoutputoctets=2048,
                framedipaddress="10.0.0.5",
            ),
            RadAcct(
                username="carol",
                nasipaddress="192.168.0.10",
                acctstarttime=now - timedelta(minutes=5),
                acctsessiontime=300,
                acctinputoctets=512,
                acctoutputoctets=1024,
                framedipaddress="10.0.0.6",
            ),
            RadAcct(
                username="alice",
                nasipaddress="192.168.0.11",
                acctstarttime=now - timedelta(hours=1),
                acctsessiontime=3600,
                acctinputoctets=4096,
                acctoutputoctets=8192,
                framedipaddress="10.0.0.7",
            ),
            RadAcct(
                username="dave",
                nasipaddress="192.168.0.12",
                acctstarttime=now - timedelta(hours=2),
                acctstoptime=now - timedelta(hours=1),  # closed — excluded
                acctsessiontime=3600,
                acctinputoctets=1,
                acctoutputoctets=1,
                framedipaddress="10.0.0.8",
            ),
        ]
    )


async def test_sessions_list_with_stats(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    _seed_sessions(session)
    await session.commit()

    resp = await client.get("/api/v1/sessions", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    usernames = [s["username"] for s in body["items"]]
    # newest start first
    assert usernames == ["carol", "bob", "alice"]
    assert body["stats"] == {
        "total": 3,
        "by_nas": [
            {"nasipaddress": "192.168.0.10", "count": 2},
            {"nasipaddress": "192.168.0.11", "count": 1},
        ],
    }
    # inet columns surface as plain strings
    assert body["items"][0]["nasipaddress"] == "192.168.0.10"
    assert body["items"][0]["framedipaddress"] == "10.0.0.6"


async def test_sessions_search_and_pagination(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    _seed_sessions(session)
    await session.commit()

    resp = await client.get("/api/v1/sessions?q=carol", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["username"] == "carol"

    resp = await client.get("/api/v1/sessions?q=192.168.0.11", headers=_auth(token))
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["username"] == "alice"

    resp = await client.get("/api/v1/sessions?page=1&page_size=2", headers=_auth(token))
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3


async def test_sessions_empty_state(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.get("/api/v1/sessions", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "stats": {"total": 0, "by_nas": []},
    }


async def test_auditor_can_read_sessions(client, session):
    await _seed_admin(session, "audit", ["*:read"])
    _seed_sessions(session)
    await session.commit()

    audit_token = await _login(client, "audit")
    resp = await client.get("/api/v1/sessions", headers=_auth(audit_token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


async def test_without_sessions_read_permission_403(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)

    resp = await client.get("/api/v1/sessions", headers=_auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
