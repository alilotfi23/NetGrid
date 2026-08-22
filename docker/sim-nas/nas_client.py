"""Simulated NAS: sends periodic RADIUS Access-Requests to FreeRADIUS.

Acts as a virtual NAS device for testing the full auth path without a real
router.  The subscriber credentials come from the NetGrid database (same
rows FreeRADIUS checks via rlm_sql), so a successful Access-Accept proves
the end-to-end path: NAS → FreeRADIUS → SQL → radcheck → Access-Accept.

Protocol: RFC 2865 (RADIUS) — UDP 1812, shared secret authenticator.
"""

import hashlib
import hmac
import os
import socket
import struct
import time
from datetime import UTC, datetime

RADIUS_HOST = os.environ.get("RADIUS_HOST", "freeradius")
RADIUS_PORT = int(os.environ.get("RADIUS_PORT", "1812"))
SHARED_SECRET = os.environ.get("RADIUS_SECRET", "netgrid_radius_secret")

# Test subscriber — must exist in the NetGrid database with matching
# Cleartext-Password in radcheck.  Override via environment variables.
USERNAME = os.environ.get("NAS_USERNAME", "demo-user")
PASSWORD = os.environ.get("NAS_PASSWORD", "demo-pass")

INTERVAL = int(os.environ.get("NAS_INTERVAL", "30"))  # seconds between attempts
NAS_IP = os.environ.get("NAS_IP", "10.0.0.1")  # Framed-IP presented to FreeRADIUS


# --- RADIUS packet helpers (RFC 2865) ---


def _random_bytes(n: int) -> bytes:
    return os.urandom(n)


def _encode_password(password: str, secret: str, authenticator: bytes) -> bytes:
    """Encode Password attribute per RFC 2865 §5.2 (XOR with MD5)."""
    pwd = password.encode()
    # pad to multiple of 16 bytes
    if len(pwd) % 16:
        pwd += b"\x00" * (16 - len(pwd) % 16)
    key = secret.encode() + authenticator
    out = bytearray()
    prev = authenticator
    for i in range(0, len(pwd), 16):
        md5 = hashlib.md5(key if i == 0 else secret.encode() + bytes(out[i - 16 : i])).digest()
        block = bytes(a ^ b for a, b in zip(pwd[i : i + 16], md5))
        out.extend(block)
    return bytes(out)


def _make_attribute(attr_type: int, value: bytes) -> bytes:
    length = len(value) + 2
    return bytes([attr_type, length]) + value


def build_access_request(username: str, password: str, secret: str) -> tuple[bytes, bytes]:
    """Build a RADIUS Access-Request packet. Returns (packet, authenticator)."""
    code = 1  # Access-Request
    ident = _random_bytes(1)[0]
    authenticator = _random_bytes(16)

    attrs = b""
    # User-Name (type 1)
    attrs += _make_attribute(1, username.encode())
    # User-Password (type 2) — encoded per RFC 2865
    attrs += _make_attribute(2, _encode_password(password, secret, authenticator))
    # NAS-IP-Address (type 4)
    attrs += _make_attribute(4, socket.inet_aton(NAS_IP))
    # NAS-Port (type 5) — virtual port
    attrs += _make_attribute(5, struct.pack("!I", 1))
    # Service-Type (type 6) — Framed (2)
    attrs += _make_attribute(6, struct.pack("!I", 2))
    # Framed-IP-Address (type 8)
    attrs += _make_attribute(8, socket.inet_aton(NAS_IP))

    length = 20 + len(attrs)
    header = bytes([code, ident]) + struct.pack("!H", length) + authenticator
    return header + attrs, authenticator


def parse_response(data: bytes) -> tuple[int, dict[int, bytes]]:
    """Parse a RADIUS response. Returns (code, {type: value})."""
    code = data[0]
    length = struct.unpack("!H", data[2:4])[0]
    attrs = {}
    pos = 20
    while pos + 2 <= length:
        attr_type = data[pos]
        attr_len = data[pos + 1]
        if attr_len < 2 or pos + attr_len > length:
            break
        attrs[attr_type] = data[pos + 2 : pos + attr_len]
        pos += attr_len
    return code, attrs


RADIUS_CODES = {2: "Access-Accept", 3: "Access-Reject", 11: "Access-Challenge"}


def send_auth_request(username: str, password: str, secret: str) -> str:
    """Send one Access-Request and return the response code name."""
    packet, _ = build_access_request(username, password, secret)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    try:
        sock.sendto(packet, (RADIUS_HOST, RADIUS_PORT))
        data, _ = sock.recvfrom(4096)
        code, _ = parse_response(data)
        return RADIUS_CODES.get(code, f"Unknown({code})")
    except socket.timeout:
        return "Timeout"
    except Exception as exc:
        return f"Error({exc})"
    finally:
        sock.close()


def main() -> None:
    ts = lambda: datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[sim-nas] RADIUS client starting — {RADIUS_HOST}:{RADIUS_PORT}")
    print(f"[sim-nas] subscriber: {USERNAME}  interval: {INTERVAL}s")
    print(f"[sim-nas] shared secret: {SHARED_SECRET[:3]}***")
    print()

    attempt = 0
    while True:
        attempt += 1
        result = send_auth_request(USERNAME, PASSWORD, SHARED_SECRET)
        status = "✓" if "Accept" in result else "✗"
        print(f"[{ts()}] #{attempt:4d}  {USERNAME} → {result}  {status}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
