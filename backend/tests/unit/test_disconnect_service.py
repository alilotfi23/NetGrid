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


async def test_send_disconnect_request_round_trip_reaches_the_nas():
    """The pyrad client really sends the packet and accepts the reply.

    A UDP listener plays the NAS on an ephemeral port; the request must
    arrive with the session identity attributes and the signed Disconnect-
    ACK must come back. Runs on Windows too — importing the disconnect
    service installs the select.poll() stand-in pyrad needs there.
    """
    import asyncio
    import hashlib
    import hmac
    import queue
    import socket
    import struct
    import threading

    secret = b"roundtrip-secret"
    received: queue.Queue = queue.Queue()

    def rad_attr(attr_type: int, value: bytes) -> bytes:
        return bytes([attr_type, len(value) + 2]) + value

    def decode_attributes(raw: bytes) -> dict[int, bytes]:
        attrs: dict[int, bytes] = {}
        pos = 20
        while pos + 2 <= len(raw):
            attr_type, length = raw[pos], raw[pos + 1]
            if length < 2 or pos + length > len(raw):
                break
            attrs[attr_type] = raw[pos + 2 : pos + length]
            pos += length
        return attrs

    def nas_server(sock: socket.socket) -> None:
        raw, addr = sock.recvfrom(4096)
        received.put(raw)
        # signed Disconnect-ACK (code 41) with a Message-Authenticator
        req_auth = raw[4:20]
        ident = raw[1]
        ma_zero = b"\x00" * 16
        attrs = rad_attr(80, ma_zero)
        code = pyrad.packet.DisconnectACK
        length = 20 + len(attrs)
        ma = hmac.new(
            secret,
            bytes([code, ident]) + struct.pack("!H", length) + req_auth + attrs,
            hashlib.md5,
        ).digest()
        attrs = rad_attr(80, ma)
        length = 20 + len(attrs)
        resp_auth = hashlib.md5(
            bytes([code, ident]) + struct.pack("!H", length) + req_auth + attrs + secret
        ).digest()
        sock.sendto(
            bytes([code, ident]) + struct.pack("!H", length) + resp_auth + attrs,
            addr,
        )

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.settimeout(5)
        port = listener.getsockname()[1]
        thread = threading.Thread(target=nas_server, args=(listener,), daemon=True)
        thread.start()

        reply_code = await asyncio.to_thread(
            disconnect_service.send_disconnect_request,
            "127.0.0.1",
            secret.decode(),
            username="bob",
            acct_session_id="abc123",
            framed_ip="10.0.0.5",
            port=port,
        )
        thread.join(timeout=5)

    assert reply_code == pyrad.packet.DisconnectACK
    raw = received.get_nowait()
    assert raw[0] == pyrad.packet.DisconnectRequest
    attrs = decode_attributes(raw)
    assert attrs[1] == b"bob"  # User-Name
    assert attrs[44] == b"abc123"  # Acct-Session-Id
    assert socket.inet_ntoa(attrs[8]) == "10.0.0.5"  # Framed-IP-Address
    assert 80 in attrs  # Message-Authenticator was on the wire


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
