"""RFC 5176 CoA/Disconnect responder for the sim-nas container.

A minimal RADIUS CoA server (UDP 3799) that makes the NetGrid disconnect
path testable end to end: FastAPI's pyrad client sends a
Disconnect-Request signed with the NAS shared secret, and this responder
validates it and replies Disconnect-ACK — so quota enforcement and manual
session disconnects get a real ACK (and a real audit ``result: "ack"``)
instead of timing out against an unreachable IP.

Wire format matches pyrad 2.5.x exactly (it is what the NetGrid backend
sends — see app/services/disconnect.py):

* Disconnect-Request / CoA-Request Request Authenticator:
      MD5(Code + Identifier + Length + 16 zero octets + Attributes + Secret)
* Request Message-Authenticator (type 80, if present):
      HMAC-MD5(Secret, Code + Identifier + Length + 16 zero octets
                        + Attributes with MA zeroed)
* Disconnect-ACK Response Authenticator:
      MD5(Code + Identifier + Length + Request Authenticator
          + Attributes + Secret)
* Reply Message-Authenticator (only when the request carried one, computed
  over the request's authenticator — pyrad's reply-side MA math).

The responder ACKs every *authentic* Disconnect/CoA-Request: it is a demo
device, not a router with a real session table. Packets that fail the
shared-secret checks are dropped (no reply — what a real NAS does), with a
log line. Pure standard library, so it runs on the same alpine image as
nas_client.py with no extra deps.

Usage:
    python3 coa_server.py                 # serve on 0.0.0.0:3799
    python3 coa_server.py --selftest      # self-check the packet math
"""

import argparse
import hashlib
import hmac
import logging
import os
import socket
import struct
import time

# --- RADIUS packet codes (RFC 2865 / RFC 5176) ---
DISCONNECT_REQUEST = 40
DISCONNECT_ACK = 41
DISCONNECT_NAK = 42
COA_REQUEST = 43
COA_ACK = 44

# Attribute types we care about for logging.
ATTR_USER_NAME = 1
ATTR_FRAMED_IP = 8
ATTR_ACCT_SESSION_ID = 44
ATTR_MESSAGE_AUTHENTICATOR = 80

# RFC 5176 reserves 3799 for CoA/Disconnect traffic (pyrad's coaport).
DEFAULT_PORT = 3799

_SECRET = os.environ.get("RADIUS_SECRET", "netgrid_radius_secret").encode()
_REPLY_CODES = {
    DISCONNECT_REQUEST: DISCONNECT_ACK,
    COA_REQUEST: COA_ACK,
}

logger = logging.getLogger("coa-server")


# ---------------------------------------------------------------------------
# Packet math (pure functions — unit-tested, also used by --selftest)
# ---------------------------------------------------------------------------


def parse_packet(raw: bytes) -> tuple[int, int, bytes, dict[int, list[bytes]]] | None:
    """Parse a RADIUS packet. Returns (code, id, authenticator, attributes)."""
    if len(raw) < 20:
        return None
    code, ident, length = struct.unpack("!BBH", raw[0:4])
    if length < 20 or length > len(raw):
        return None
    authenticator = raw[4:20]
    attrs: dict[int, list[bytes]] = {}
    pos = 20
    while pos + 2 <= length:
        attr_type, attr_len = raw[pos], raw[pos + 1]
        if attr_len < 2 or pos + attr_len > length:
            return None
        attrs.setdefault(attr_type, []).append(raw[pos + 2 : pos + attr_len])
        pos += attr_len
    if pos != length:
        return None
    return code, ident, authenticator, attrs


def _request_authenticator(raw: bytes, secret: bytes) -> bytes:
    """RFC 5176 request authenticator: MD5 with the authenticator field zeroed."""
    return hashlib.md5(raw[0:4] + b"\x00" * 16 + raw[20:] + secret).digest()


def _zero_ma(raw: bytes) -> bytes:
    """Raw attributes with the Message-Authenticator value zeroed, in place.

    Operates on the raw bytes so the exact attribute order (and any vendor
    attributes) is preserved — pyrad computes its HMAC over the encoded
    attribute stream, so order must not be reshuffled.
    """
    out = bytearray()
    pos = 20
    while pos + 2 <= len(raw):
        attr_type, attr_len = raw[pos], raw[pos + 1]
        if attr_len < 2 or pos + attr_len > len(raw):
            break
        if attr_type == ATTR_MESSAGE_AUTHENTICATOR and attr_len == 18:
            out += bytes([ATTR_MESSAGE_AUTHENTICATOR, 18]) + b"\x00" * 16
        else:
            out += raw[pos : pos + attr_len]
        pos += attr_len
    return bytes(out)


def verify_request(raw: bytes, secret: bytes) -> tuple[bool, str]:
    """Validate a Disconnect/CoA-Request. Returns (ok, reason).

    Checks the RFC 5176 Request Authenticator and, when present, the
    Message-Authenticator (HMAC-MD5). Both use the 16-zero-octet
    authenticator substitution, matching pyrad's CoAPacket encoding.
    """
    if len(raw) < 20:
        return False, "packet too short"
    if not raw[0] in _REPLY_CODES:
        return False, f"not a CoA/Disconnect request (code {raw[0]})"
    expected_auth = _request_authenticator(raw, secret)
    if not hmac.compare_digest(expected_auth, raw[4:20]):
        return False, "bad request authenticator"
    if ATTR_MESSAGE_AUTHENTICATOR not in _attr_types(raw):
        return True, "authentic (no Message-Authenticator)"
    ma_value = _find_ma(raw)
    if ma_value is None or len(ma_value) != 16:
        return False, "malformed Message-Authenticator"
    expected_ma = hmac.new(
        secret, raw[0:4] + b"\x00" * 16 + _zero_ma(raw), digestmod="md5"
    ).digest()
    if not hmac.compare_digest(expected_ma, ma_value):
        return False, "bad Message-Authenticator"
    return True, "authentic"


def _attr_types(raw: bytes) -> set[int]:
    types: set[int] = set()
    pos = 20
    while pos + 2 <= len(raw):
        attr_type, attr_len = raw[pos], raw[pos + 1]
        if attr_len < 2 or pos + attr_len > len(raw):
            break
        types.add(attr_type)
        pos += attr_len
    return types


def _find_ma(raw: bytes) -> bytes | None:
    pos = 20
    while pos + 2 <= len(raw):
        attr_type, attr_len = raw[pos], raw[pos + 1]
        if attr_len < 2 or pos + attr_len > len(raw):
            break
        if attr_type == ATTR_MESSAGE_AUTHENTICATOR and attr_len == 18:
            return raw[pos + 2 : pos + 18]
        pos += attr_len
    return None


def build_disconnect_ack(raw: bytes, secret: bytes) -> bytes | None:
    """Build a Disconnect/CoA-ACK for a verified request, or None if invalid."""
    parsed = parse_packet(raw)
    if parsed is None:
        return None
    code, ident, request_auth, _ = parsed
    reply_code = _REPLY_CODES.get(code)
    if reply_code is None:
        return None

    # Reply attributes: echo a Message-Authenticator only when the request
    # carried one (RFC 5176 §3.5), computed over the request's authenticator.
    request_had_ma = ATTR_MESSAGE_AUTHENTICATOR in _attr_types(raw)
    attrs = b""
    if request_had_ma:
        attr = bytes([ATTR_MESSAGE_AUTHENTICATOR, 18]) + b"\x00" * 16
        length = 20 + len(attr)
        header = struct.pack("!BBH", reply_code, ident, length)
        ma = hmac.new(
            secret, header + request_auth + attr, digestmod="md5"
        ).digest()
        attrs = bytes([ATTR_MESSAGE_AUTHENTICATOR, 18]) + ma

    length = 20 + len(attrs)
    header = struct.pack("!BBH", reply_code, ident, length)
    authenticator = hashlib.md5(
        header + request_auth + attrs + secret
    ).digest()
    return header + authenticator + attrs


def handle_packet(raw: bytes, secret: bytes) -> bytes | None:
    """Handle one inbound datagram. Returns the reply bytes, or None to drop."""
    parsed = parse_packet(raw)
    if parsed is None:
        logger.warning("dropping malformed packet (%d bytes)", len(raw))
        return None
    code, ident, _, _ = parsed
    ok, reason = verify_request(raw, secret)
    if not ok:
        logger.warning("dropping code %d id %d: %s", code, ident, reason)
        return None
    reply = build_disconnect_ack(raw, secret)
    if reply is None:
        logger.warning("dropping code %d id %d: cannot build reply", code, ident)
        return None
    return reply


# ---------------------------------------------------------------------------
# Network loop
# ---------------------------------------------------------------------------


def serve(port: int = DEFAULT_PORT, secret: bytes = _SECRET) -> None:
    """Block forever answering CoA/Disconnect-Requests on UDP `port`."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(1.0)
    logger.info("CoA responder listening on 0.0.0.0:%d/udp (secret %s***)",
                port, secret[:3].decode(errors="replace"))
    while True:
        try:
            raw, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            time.sleep(0.2)
            continue
        parsed = parse_packet(raw)
        reply = handle_packet(raw, secret)
        if parsed is None:
            continue
        code, ident, _, attrs = parsed
        identity = _describe(attrs)
        if reply is None:
            logger.info("dropped %s id %d from %s%s",
                        _code_name(code), ident, addr, identity)
            continue
        reply_code = reply[0]
        sock.sendto(reply, addr)
        logger.info("replied %s id %d to %s%s",
                    _code_name(reply_code), ident, addr, identity)


def _describe(attrs: dict[int, list[bytes]]) -> str:
    parts: list[str] = []
    if ATTR_USER_NAME in attrs:
        parts.append(f" user={attrs[ATTR_USER_NAME][0].decode(errors='replace')!r}")
    if ATTR_ACCT_SESSION_ID in attrs:
        parts.append(f" session={attrs[ATTR_ACCT_SESSION_ID][0].decode(errors='replace')!r}")
    if ATTR_FRAMED_IP in attrs:
        parts.append(f" framed-ip={socket.inet_ntoa(attrs[ATTR_FRAMED_IP][0])}")
    return "".join(parts)


def _code_name(code: int) -> str:
    return {
        DISCONNECT_REQUEST: "Disconnect-Request",
        DISCONNECT_ACK: "Disconnect-ACK",
        DISCONNECT_NAK: "Disconnect-NAK",
        COA_REQUEST: "CoA-Request",
        COA_ACK: "CoA-ACK",
    }.get(code, f"code {code}")


# ---------------------------------------------------------------------------
# Self-test: build a pyrad-style Disconnect-Request in-process and verify
# the full round trip (request auth + MA validation -> ACK -> reply checks).
# ---------------------------------------------------------------------------


def _build_pyrad_style_request(
    secret: bytes, username: str = "grace.hopper", ident: int = 0x42
) -> bytes:
    """Reproduce pyrad CoAPacket.RequestPacket() wire bytes for code 40."""
    name_attr = bytes([ATTR_USER_NAME, len(username) + 2]) + username.encode()

    # 1. Message-Authenticator computed over attrs with MA zeroed, and the
    #    authenticator field treated as 16 zero octets (pyrad line ~129-155).
    ma_zeroed = name_attr + bytes([ATTR_MESSAGE_AUTHENTICATOR, 18]) + b"\x00" * 16
    header = bytes([DISCONNECT_REQUEST, ident]) + struct.pack("!H", 20 + len(ma_zeroed))
    ma = hmac.new(secret, header + b"\x00" * 16 + ma_zeroed, digestmod="md5").digest()

    # 2. Request authenticator: MD5 over the full packet with the authenticator
    #    field zeroed (pyrad line ~881).
    attrs = name_attr + bytes([ATTR_MESSAGE_AUTHENTICATOR, 18]) + ma
    header = bytes([DISCONNECT_REQUEST, ident]) + struct.pack("!H", 20 + len(attrs))
    auth = hashlib.md5(header + b"\x00" * 16 + attrs + secret).digest()
    return header + auth + attrs


def selftest() -> int:
    secret = b"testing123"
    raw = _build_pyrad_style_request(secret)
    ok, reason = verify_request(raw, secret)
    assert ok, f"request failed verification: {reason}"

    reply = handle_packet(raw, secret)
    assert reply is not None, "no reply for valid request"
    reply_code, ident, length = struct.unpack("!BBH", reply[0:4])
    assert reply_code == DISCONNECT_ACK, f"expected ACK, got {reply_code}"
    assert ident == 0x42, "ACK must echo the request id"
    assert length == len(reply)

    # Reply checks exactly as pyrad VerifyReply does them.
    request_auth = raw[4:20]
    assert hashlib.md5(reply[0:4] + request_auth + reply[20:] + secret).digest() == reply[4:20], \
        "pyrad-style response authenticator check failed"
    ma = _find_ma(reply)
    assert ma is not None and len(ma) == 16, "ACK should echo Message-Authenticator"
    zeroed = _zero_ma(reply)
    assert hmac.new(secret, reply[0:4] + request_auth + zeroed, digestmod="md5").digest() == ma, \
        "ACK Message-Authenticator check failed"

    # Wrong secret must be dropped (no reply), like a real NAS.
    assert handle_packet(raw, b"wrong-secret") is None, "bad secret must drop"
    # Tampered payload must be dropped.
    tampered = bytearray(raw)
    tampered[26] ^= 0xFF  # flip a bit inside the User-Name value
    assert handle_packet(bytes(tampered), secret) is None, "tampered packet must drop"

    print("selftest OK: pyrad-style Disconnect-Request -> Disconnect-ACK verified")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    parser = argparse.ArgumentParser(description="sim-nas RFC 5176 CoA responder")
    parser.add_argument("--port", type=int, default=int(os.environ.get("COA_PORT", DEFAULT_PORT)))
    parser.add_argument("--selftest", action="store_true", help="run in-process packet self-test")
    args = parser.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    serve(port=args.port)


if __name__ == "__main__":
    main()
