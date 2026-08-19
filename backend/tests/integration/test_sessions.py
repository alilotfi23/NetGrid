"""Integration tests for the live-sessions API (Phase 9)."""

from datetime import UTC, datetime, timedelta

import pyrad.client
import pyrad.packet
from sqlalchemy import select

from app.core.security import encrypt_secret, hash_password
from app.models.audit import AuditLog
from app.models.nas import NasDevice
from app.models.radius import Nas, RadAcct
from app.models.rbac import Admin, Permission, Role
from app.services import disconnect as disconnect_service


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
            {"nasipaddress": "192.168.0.10", "count": 2, "nas_shortname": None},
            {"nasipaddress": "192.168.0.11", "count": 1, "nas_shortname": None},
        ],
    }
    # inet columns surface as plain strings
    assert body["items"][0]["nasipaddress"] == "192.168.0.10"
    assert body["items"][0]["nas_shortname"] is None
    assert body["items"][0]["framedipaddress"] == "10.0.0.6"


async def test_sessions_resolve_nas_shortnames(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    session.add(
        Nas(nasname="192.168.0.10", shortname="edge-r1", type="mikrotik", secret="radius_secret")
    )
    _seed_sessions(session)
    await session.commit()

    resp = await client.get("/api/v1/sessions", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    by_ip = {s["nasipaddress"]: s["nas_shortname"] for s in body["items"]}
    assert by_ip["192.168.0.10"] == "edge-r1"
    assert by_ip["192.168.0.11"] is None
    assert body["stats"]["by_nas"] == [
        {"nasipaddress": "192.168.0.10", "count": 2, "nas_shortname": "edge-r1"},
        {"nasipaddress": "192.168.0.11", "count": 1, "nas_shortname": None},
    ]

    # q matches the resolved shortname too
    resp = await client.get("/api/v1/sessions?q=edge-r1", headers=_auth(token))
    body = resp.json()
    assert body["total"] == 2
    assert {s["username"] for s in body["items"]} == {"bob", "carol"}


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


# ---------------------------------------------------------------------------
# Disconnect (RFC 5176 Disconnect-Request via pyrad)
# ---------------------------------------------------------------------------


def _seed_disconnectable(session) -> RadAcct:
    """An inventory NAS + an open session on it, for disconnect tests."""
    session.add(
        NasDevice(
            name="edge-r1",
            ip_address="192.168.0.10",
            shortname="edge-r1",
            nas_type="mikrotik",
            secret_encrypted=encrypt_secret("topsecret"),
            is_active=True,
        )
    )
    row = RadAcct(
        username="bob",
        nasipaddress="192.168.0.10",
        acctstarttime=datetime.now(UTC) - timedelta(minutes=10),
        acctsessionid="sess-1",
        acctsessiontime=600,
        acctinputoctets=1024,
        acctoutputoctets=2048,
        framedipaddress="10.0.0.5",
    )
    session.add(row)
    return row


async def test_disconnect_ack_success(client, session, monkeypatch):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    row = _seed_disconnectable(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    resp = await client.post(f"/api/v1/sessions/{row.id}/disconnect", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"status": "disconnected"}

    entries = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "disconnect")))
        .scalars()
        .all()
    )
    assert len(entries) == 1  # login also audits, so filter by action
    entry = entries[0]
    assert entry.resource == "sessions"
    assert entry.resource_id == str(row.id)
    assert entry.metadata_ == {
        "username": "bob",
        "nasipaddress": "192.168.0.10",
        "result": "ack",
    }


async def test_disconnect_requires_sessions_disconnect_permission(client, session):
    # sessions:read alone must not allow the disconnect action
    await _seed_admin(session, "boss", ["sessions:read"])
    token = await _login(client)

    resp = await client.post("/api/v1/sessions/1/disconnect", headers=_auth(token))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_auditor_cannot_disconnect(client, session):
    await _seed_admin(session, "audit", ["*:read"])
    audit_token = await _login(client, "audit")

    resp = await client.post("/api/v1/sessions/1/disconnect", headers=_auth(audit_token))
    assert resp.status_code == 403


async def test_disconnect_unknown_session_404(client, session, monkeypatch):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    resp = await client.post("/api/v1/sessions/99999/disconnect", headers=_auth(token))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_disconnect_nak_409(client, session, monkeypatch):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    row = _seed_disconnectable(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectNAK
    )

    resp = await client.post(f"/api/v1/sessions/{row.id}/disconnect", headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_disconnect_timeout_502(client, session, monkeypatch):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    row = _seed_disconnectable(session)
    await session.commit()

    def boom(*a, **k):
        raise pyrad.client.Timeout

    monkeypatch.setattr(disconnect_service, "send_disconnect_request", boom)
    resp = await client.post(f"/api/v1/sessions/{row.id}/disconnect", headers=_auth(token))
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "BAD_GATEWAY"


async def test_disconnect_no_active_nas_409(client, session, monkeypatch):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    row = RadAcct(
        username="bob",
        nasipaddress="192.168.0.99",  # no inventory NAS for this IP
        acctstarttime=datetime.now(UTC) - timedelta(minutes=10),
        acctsessionid="sess-2",
    )
    session.add(row)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    resp = await client.post(f"/api/v1/sessions/{row.id}/disconnect", headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
