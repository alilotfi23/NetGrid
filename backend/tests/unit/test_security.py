import jwt
import pytest

from app.core import security
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError


def test_password_hash_roundtrip():
    hashed = security.hash_password("s3cret")
    assert hashed != "s3cret"
    assert security.verify_password("s3cret", hashed)


def test_password_hash_is_salted():
    assert security.hash_password("same") != security.hash_password("same")


def test_wrong_password_rejected():
    hashed = security.hash_password("right")
    assert not security.verify_password("wrong", hashed)


def test_access_token_roundtrip():
    token = security.create_access_token("7")
    payload = security.decode_token(token, expected_type="access")
    assert payload["sub"] == "7"
    assert payload["type"] == "access"
    assert payload["jti"]
    assert payload["exp"]


def test_access_token_embeds_perm_version():
    token = security.create_access_token("7", perm_version="abc123")
    payload = security.decode_token(token, expected_type="access")
    assert payload["perm_version"] == "abc123"


def test_access_token_without_perm_version():
    token = security.create_access_token("7")
    payload = security.decode_token(token, expected_type="access")
    assert "perm_version" not in payload


def test_refresh_token_roundtrip_returns_jti():
    token, jti = security.create_refresh_token("7")
    payload = security.decode_token(token, expected_type="refresh")
    assert payload["sub"] == "7"
    assert payload["jti"] == jti


def test_decode_rejects_wrong_type():
    token = security.create_access_token("7")
    with pytest.raises(UnauthorizedError):
        security.decode_token(token, expected_type="refresh")


def test_decode_rejects_wrong_secret():
    token = jwt.encode({"sub": "7"}, "not-the-secret", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        security.decode_token(token)


def test_decode_rejects_expired_token():
    settings = get_settings()
    expired = jwt.encode(
        {"sub": "7", "type": "access", "jti": "x", "iat": 0, "exp": 0},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        security.decode_token(expired)


def test_decode_rejects_garbage():
    with pytest.raises(UnauthorizedError):
        security.decode_token("not.a.jwt")
