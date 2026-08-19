"""Unit tests for the RFC 5176 disconnect service (Phase 9 write side)."""

from datetime import UTC, datetime, timedelta

import pyrad.client
import pyrad.packet
import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, GatewayError, NotFoundError
from app.core.security import encrypt_secret, hash_password
from app.models.audit import AuditLog
from app.models.nas import NasDevice
from app.models.radius import RadAcct
from app.models.rbac import Admin
from app.services import disconnect as disconnect_service


async def _seed_admin(session) -> Admin:
    admin = Admin(
        username="root",
        email="root@netgrid.local",
        password_hash=hash_password("x"),
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    return admin


def _seed_session(session, *, username="bob", nas="192.168.0.10", stop=None) -> RadAcct:
    row = RadAcct(
        username=username,
        nasipaddress=nas,
        acctstarttime=datetime.now(UTC) - timedelta(minutes=10),
        acctstoptime=stop,
        acctsessionid="abc123",
        acctsessiontime=600,
        acctinputoctets=1024,
        acctoutputoctets=2048,
        framedipaddress="10.0.0.5",
    )
    session.add(row)
    return row


def _seed_nas(session, *, ip="192.168.0.10", secret="topsecret", is_active=True) -> NasDevice:
    device = NasDevice(
        name=f"nas-{ip}",
        ip_address=ip,
        shortname=f"nas-{ip}",
        nas_type="other",
        secret_encrypted=encrypt_secret(secret),
        is_active=is_active,
    )
    session.add(device)
    return device


async def _audit_rows(session) -> list[AuditLog]:
    return list((await session.execute(select(AuditLog))).scalars().all())


async def test_disconnect_ack_returns_disconnected(session, monkeypatch):
    admin = await _seed_admin(session)
    row = _seed_session(session)
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    status = await disconnect_service.disconnect_session(
        session, session_id=row.id, actor_id=admin.id
    )
    assert status == "disconnected"

    (entry,) = await _audit_rows(session)
    assert entry.action == "disconnect"
    assert entry.resource == "sessions"
    assert entry.resource_id == str(row.id)
    assert entry.metadata_ == {
        "username": "bob",
        "nasipaddress": "192.168.0.10",
        "result": "ack",
    }


async def test_disconnect_sends_username_session_id_and_framed_ip(session, monkeypatch):
    admin = await _seed_admin(session)
    row = _seed_session(session)
    _seed_nas(session, secret="s3cret")
    await session.commit()
    captured: dict[str, object] = {}

    def fake(nas_ip, secret, *, username, acct_session_id, framed_ip):
        captured.update(
            nas_ip=nas_ip,
            secret=secret,
            username=username,
            acct_session_id=acct_session_id,
            framed_ip=framed_ip,
        )
        return pyrad.packet.DisconnectACK

    monkeypatch.setattr(disconnect_service, "send_disconnect_request", fake)
    await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=admin.id)

    assert captured == {
        "nas_ip": "192.168.0.10",
        "secret": "s3cret",  # decrypted plaintext — what pyrad signs with
        "username": "bob",
        "acct_session_id": "abc123",
        "framed_ip": "10.0.0.5",
    }


async def test_disconnect_nak_raises_conflict_and_audits(session, monkeypatch):
    admin = await _seed_admin(session)
    row = _seed_session(session)
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectNAK
    )

    with pytest.raises(ConflictError):
        await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=admin.id)
    (entry,) = await _audit_rows(session)
    assert entry.metadata_["result"] == "nak"


async def test_disconnect_timeout_raises_gateway_and_audits(session, monkeypatch):
    admin = await _seed_admin(session)
    row = _seed_session(session)
    _seed_nas(session)
    await session.commit()

    def boom(*a, **k):
        raise pyrad.client.Timeout

    monkeypatch.setattr(disconnect_service, "send_disconnect_request", boom)
    with pytest.raises(GatewayError):
        await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=admin.id)
    (entry,) = await _audit_rows(session)
    assert entry.metadata_["result"] == "timeout"


async def test_disconnect_unexpected_reply_raises_gateway(session, monkeypatch):
    admin = await _seed_admin(session)
    row = _seed_session(session)
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service,
        "send_disconnect_request",
        lambda *a, **k: 44,  # CoA-ACK
    )

    with pytest.raises(GatewayError):
        await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=admin.id)
    (entry,) = await _audit_rows(session)
    assert entry.metadata_["result"] == "unexpected_code_44"


async def test_disconnect_unknown_session_not_found(session, monkeypatch):
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )
    with pytest.raises(NotFoundError):
        await disconnect_service.disconnect_session(session, session_id=99999, actor_id=1)
    assert await _audit_rows(session) == []


async def test_disconnect_closed_session_conflict(session, monkeypatch):
    row = _seed_session(session, stop=datetime.now(UTC))
    _seed_nas(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    with pytest.raises(ConflictError):
        await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=1)
    assert await _audit_rows(session) == []


async def test_disconnect_without_nas_device_conflict(session, monkeypatch):
    row = _seed_session(session)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    with pytest.raises(ConflictError):
        await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=1)
    assert await _audit_rows(session) == []


async def test_disconnect_inactive_nas_device_conflict(session, monkeypatch):
    row = _seed_session(session)
    _seed_nas(session, is_active=False)
    await session.commit()
    monkeypatch.setattr(
        disconnect_service, "send_disconnect_request", lambda *a, **k: pyrad.packet.DisconnectACK
    )

    with pytest.raises(ConflictError):
        await disconnect_service.disconnect_session(session, session_id=row.id, actor_id=1)
    assert await _audit_rows(session) == []
