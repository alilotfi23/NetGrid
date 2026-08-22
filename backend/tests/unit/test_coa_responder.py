"""Unit tests for the sim-nas RFC 5176 CoA responder packet math.

The responder lives in docker/sim-nas (pure stdlib, no project imports),
so these tests load it by file path and exercise the pure packet functions
in-process — no sockets, no Docker, runs anywhere pytest runs. They pin the
wire format to what the pyrad client in app/services/disconnect.py encodes
(the request/response authenticator and Message-Authenticator formulas).
"""

import hashlib
import hmac
import importlib.util
import struct
from pathlib import Path

_SIM_NAS = Path(__file__).resolve().parents[3] / "docker" / "sim-nas"
_COA_PATH = _SIM_NAS / "coa_server.py"

spec = importlib.util.spec_from_file_location("sim_nas_coa_server", _COA_PATH)
assert spec is not None and spec.loader is not None
coa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coa)

SECRET = b"netgrid_radius_secret"


def build_request(
    secret: bytes, username: str = "grace.hopper", ident: int = 0x42, code: int = 40
) -> bytes:
    """Reproduce pyrad CoAPacket.RequestPacket() wire bytes (code 40 or 43)."""
    name_attr = bytes([coa.ATTR_USER_NAME, len(username) + 2]) + username.encode()
    ma_zeroed = name_attr + bytes([coa.ATTR_MESSAGE_AUTHENTICATOR, 18]) + b"\x00" * 16
    header = bytes([code, ident]) + struct.pack("!H", 20 + len(ma_zeroed))
    ma = hmac.new(secret, header + b"\x00" * 16 + ma_zeroed, digestmod="md5").digest()
    attrs = name_attr + bytes([coa.ATTR_MESSAGE_AUTHENTICATOR, 18]) + ma
    header = bytes([code, ident]) + struct.pack("!H", 20 + len(attrs))
    auth = hashlib.md5(header + b"\x00" * 16 + attrs + secret).digest()
    return header + auth + attrs


class TestVerifyRequest:
    def test_authentic_request_passes(self) -> None:
        ok, reason = coa.verify_request(build_request(SECRET), SECRET)
        assert ok, reason

    def test_wrong_secret_fails(self) -> None:
        ok, reason = coa.verify_request(build_request(SECRET), b"wrong-secret")
        assert not ok
        assert "authenticator" in reason

    def test_tampered_payload_fails(self) -> None:
        raw = bytearray(build_request(SECRET))
        raw[26] ^= 0xFF  # flip a bit inside the User-Name value
        ok, reason = coa.verify_request(bytes(raw), SECRET)
        assert not ok

    def test_non_coa_code_rejected(self) -> None:
        raw = bytearray(build_request(SECRET))
        raw[0] = 1  # Access-Request is not a CoA code
        ok, reason = coa.verify_request(bytes(raw), SECRET)
        assert not ok
        assert "not a CoA/Disconnect" in reason

    def test_short_packet_rejected(self) -> None:
        ok, reason = coa.verify_request(b"\x00" * 12, SECRET)
        assert not ok


class TestDisconnectAck:
    def test_ack_shape(self) -> None:
        raw = build_request(SECRET, ident=0x2A)
        reply = coa.handle_packet(raw, SECRET)
        assert reply is not None
        code, ident, length = struct.unpack("!BBH", reply[0:4])
        assert code == coa.DISCONNECT_ACK
        assert ident == 0x2A  # echoes the request id (pyrad VerifyReply requires it)
        assert length == len(reply)

    def test_ack_passes_pyrad_verify_reply(self) -> None:
        """The exact checks pyrad client.VerifyReply applies to the reply."""
        raw = build_request(SECRET)
        reply = coa.handle_packet(raw, SECRET)
        assert reply is not None
        request_auth = raw[4:20]
        # Response authenticator: MD5(code+id+len + request_auth + attrs + secret)
        assert hashlib.md5(reply[0:4] + request_auth + reply[20:] + SECRET).digest() == reply[4:20]
        # Reply echoes Message-Authenticator, computed over the request auth.
        ma = coa._find_ma(reply)
        assert ma is not None and len(ma) == 16
        assert (
            hmac.new(
                SECRET, reply[0:4] + request_auth + coa._zero_ma(reply), digestmod="md5"
            ).digest()
            == ma
        )

    def test_bad_secret_dropped_silently(self) -> None:
        assert coa.handle_packet(build_request(SECRET), b"wrong-secret") is None

    def test_tampered_packet_dropped(self) -> None:
        raw = bytearray(build_request(SECRET))
        raw[26] ^= 0xFF
        assert coa.handle_packet(bytes(raw), SECRET) is None

    def test_coa_request_also_acked(self) -> None:
        raw = build_request(SECRET, code=coa.COA_REQUEST)
        reply = coa.handle_packet(raw, SECRET)
        assert reply is not None
        assert reply[0] == coa.COA_ACK


class TestParsePacket:
    def test_attributes_parsed(self) -> None:
        raw = build_request(SECRET)
        parsed = coa.parse_packet(raw)
        assert parsed is not None
        code, ident, auth, attrs = parsed
        assert code == coa.DISCONNECT_REQUEST
        assert len(auth) == 16
        assert coa.ATTR_USER_NAME in attrs
        assert attrs[coa.ATTR_USER_NAME][0] == b"grace.hopper"
        assert coa.ATTR_MESSAGE_AUTHENTICATOR in attrs

    def test_malformed_returns_none(self) -> None:
        assert coa.parse_packet(b"") is None
        assert coa.parse_packet(b"\x00" * 19) is None
        # Length field says 40 but only 20 bytes present.
        assert coa.parse_packet(b"\x28\x01\x00\x28" + b"\x00" * 16) is None
