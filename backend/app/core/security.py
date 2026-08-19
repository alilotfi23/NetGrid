"""Password hashing (argon2), JWT primitives, and Fernet secret encryption."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from cryptography.fernet import Fernet
from jwt import InvalidTokenError
from passlib.context import CryptContext

from .config import get_settings
from .exceptions import UnauthorizedError

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(password: str) -> str:
    hashed: str = pwd_context.hash(password)
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    result: bool = pwd_context.verify(plain, hashed)
    return result


def _encode(
    subject: str, token_type: str, ttl: timedelta, perm_version: str | None = None
) -> tuple[str, str]:
    """Encode a JWT; returns (token, jti) so logout/rotation can revoke it."""
    settings = get_settings()
    jti = uuid4().hex
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }
    if perm_version is not None:
        payload["perm_version"] = perm_version
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, jti


def create_access_token(subject: str, perm_version: str | None = None) -> str:
    ttl = timedelta(minutes=get_settings().jwt_access_ttl_minutes)
    token, _ = _encode(subject, TOKEN_TYPE_ACCESS, ttl, perm_version=perm_version)
    return token


def create_refresh_token(subject: str) -> tuple[str, str]:
    """Returns (token, jti). The jti is what logout/rotation blacklists."""
    ttl = timedelta(days=get_settings().jwt_refresh_ttl_days)
    return _encode(subject, TOKEN_TYPE_REFRESH, ttl)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Decode + validate a JWT. Raises UnauthorizedError on any failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
    if expected_type is not None and payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")
    return payload


# ---------------------------------------------------------------------------
# Fernet encryption for NAS shared secrets (Phase 7)
# ---------------------------------------------------------------------------


def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY is not configured")
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    """Encrypt a NAS shared secret at rest (Fernet, authenticated)."""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a NAS shared secret back to plaintext (for the nas table)."""
    return _fernet().decrypt(token.encode()).decode()
