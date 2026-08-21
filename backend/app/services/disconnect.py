"""RFC 5176 Disconnect-Request sender for live sessions (Phase 9, write side).

The CoA/disconnect path is a direct pyrad client call from FastAPI to the NAS
(CLAUDE.md decision — a client-library call, not a FreeRADIUS proxy bridge).
The request is signed with the NAS device's shared secret (decrypted from
nas_devices.secret_encrypted) and sent to the NAS's RADIUS disconnect port
(3799/udp). The NAS replies Disconnect-ACK/NAK; the radacct row closes when
the NAS later sends its Accounting-Stop — FastAPI never writes radacct.
"""

import asyncio
import select as os_select
from pathlib import Path
from typing import Any, cast

import pyrad.client
import pyrad.dictionary
import pyrad.packet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, GatewayError, NotFoundError
from app.core.security import decrypt_secret
from app.models.nas import NasDevice
from app.models.radius import RadAcct
from app.services import audit as audit_service

# RFC 5176 reserves 3799 for CoA and Disconnect traffic (pyrad's coaport).
DISCONNECT_PORT = 3799

# pyrad's client polls its socket with select.poll(), which POSIX provides
# but Windows does not — without a stand-in, the disconnect path crashes
# before a single byte is sent on Windows dev hosts (the compose backend,
# running Linux, is unaffected). Patching the shared module object (pyrad
# looks up select.poll at call time) installs a select.select()-based
# replacement so the pyrad Client can wait for the NAS reply everywhere.
if not hasattr(os_select, "poll"):

    class _SelectPoll:
        """Minimal select.poll() stand-in built on select.select()."""

        def __init__(self) -> None:
            # Any: pyrad registers socket objects (or fds) here; select()
            # only reads them, so the exact type is irrelevant.
            self._readers: list[Any] = []

        def register(self, fd: object, _events: int = 0) -> None:
            self._readers.append(fd)

        def unregister(self, fd: object) -> None:
            try:
                self._readers.remove(fd)
            except ValueError:
                pass

        def poll(self, timeout_ms: int | None = None) -> list[tuple[object, int]]:
            timeout = None if timeout_ms is None else timeout_ms / 1000.0
            readable, _, _ = os_select.select(self._readers, [], [], timeout)
            return [(fd, os_select.POLLIN) for fd in readable]  # type: ignore[attr-defined]

    os_select.POLLIN = 0x0001  # type: ignore[attr-defined]
    os_select.poll = _SelectPoll  # type: ignore[attr-defined]

# pyrad does not ship a dictionary, and FreeRADIUS's full dictionary is not
# present in the backend image — vendor the handful of attributes we encode.
_DICTIONARY_FILE = Path(__file__).parent / "radius_dictionary.txt"


def send_disconnect_request(
    nas_ip: str,
    secret: str,
    *,
    username: str,
    acct_session_id: str | None,
    framed_ip: str | None,
    port: int = DISCONNECT_PORT,
) -> int:
    """Send one Disconnect-Request to the NAS and return the reply code.

    Synchronous (pyrad is a blocking socket client) — callers run this via
    asyncio.to_thread. Raises pyrad.client.Timeout when the NAS does not
    reply within the retry budget. ``port`` defaults to the RFC 5176
    disconnect port (3799) and is injectable for tests.
    """
    dictionary = pyrad.dictionary.Dictionary(str(_DICTIONARY_FILE))
    client = pyrad.client.Client(
        server=nas_ip,
        secret=secret.encode(),
        dict=dictionary,
        coaport=port,
        timeout=5,
        retries=2,
    )
    packet = pyrad.packet.CoAPacket(
        code=pyrad.packet.DisconnectRequest,
        dict=dictionary,
        secret=secret.encode(),
        message_authenticator=True,
        User_Name=username,
    )
    if acct_session_id:
        packet["Acct-Session-Id"] = acct_session_id
    if framed_ip:
        packet["Framed-IP-Address"] = framed_ip

    # pyrad 2.5.x quirk: CoAPacket.RequestPacket() builds the header *before*
    # refreshing Message-Authenticator, so the first call emits a packet whose
    # length field and Request-Authenticator predate the MA attribute —
    # FreeRADIUS drops it as "invalid Request Authenticator". Warm the packet
    # once so the wire bytes (and any retry re-encode) carry the MA and a
    # matching length/authenticator.
    packet.RequestPacket()

    # SendPacket routes CoAPacket instances to self.coaport (3799).
    reply = client.SendPacket(packet)
    return cast(int, reply.code)


async def disconnect_session(session: AsyncSession, *, session_id: int, actor_id: int) -> str:
    """Disconnect a live session by sending its NAS a Disconnect-Request.

    Resolves the open radacct row, finds the active inventory NAS for its
    IP, decrypts the shared secret, and sends the packet (off the event
    loop). Every attempt is recorded in audit_log with its outcome
    (ack/nak/timeout). Returns \"disconnected\" on Disconnect-ACK; raises
    NotFoundError (unknown/ended session), ConflictError (no active NAS or
    Disconnect-NAK) or GatewayError (no reply).
    """
    row = (
        await session.execute(select(RadAcct).where(RadAcct.id == session_id))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Session not found")
    if row.acctstoptime is not None:
        raise ConflictError("Session is no longer active")
    nas_ip = str(row.nasipaddress) if row.nasipaddress else None
    if nas_ip is None:
        raise ConflictError("Session has no NAS IP address")

    device = (
        await session.execute(select(NasDevice).where(NasDevice.ip_address == nas_ip))
    ).scalar_one_or_none()
    if device is None or not device.is_active:
        raise ConflictError("No active NAS device registered for this session")

    secret = decrypt_secret(device.secret_encrypted)
    username = row.username or ""
    metadata: dict[str, object] = {"username": username, "nasipaddress": nas_ip}

    try:
        reply_code = await asyncio.to_thread(
            send_disconnect_request,
            nas_ip,
            secret,
            username=username,
            acct_session_id=row.acctsessionid,
            framed_ip=str(row.framedipaddress) if row.framedipaddress else None,
        )
    except pyrad.client.Timeout as exc:
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="disconnect",
            resource="sessions",
            resource_id=str(session_id),
            metadata_={**metadata, "result": "timeout"},
        )
        raise GatewayError("NAS did not answer the disconnect request") from exc

    if reply_code == pyrad.packet.DisconnectNAK:
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="disconnect",
            resource="sessions",
            resource_id=str(session_id),
            metadata_={**metadata, "result": "nak"},
        )
        raise ConflictError("NAS refused the disconnect request (Disconnect-NAK)")
    if reply_code != pyrad.packet.DisconnectACK:
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="disconnect",
            resource="sessions",
            resource_id=str(session_id),
            metadata_={**metadata, "result": f"unexpected_code_{reply_code}"},
        )
        raise GatewayError(f"Unexpected reply from NAS (code {reply_code})")

    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="disconnect",
        resource="sessions",
        resource_id=str(session_id),
        metadata_={**metadata, "result": "ack"},
    )
    return "disconnected"
