"""Password hashing (argon2) and JWT primitives for admin auth."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
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


def _encode(subject: str, token_type: str, ttl: timedelta) -> tuple[str, str]:
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
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, jti


def create_access_token(subject: str) -> str:
    ttl = timedelta(minutes=get_settings().jwt_access_ttl_minutes)
    token, _ = _encode(subject, TOKEN_TYPE_ACCESS, ttl)
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
