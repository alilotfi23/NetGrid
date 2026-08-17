"""Admin authentication service: credential checks, token issuance, revocation."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.rbac import Admin

BLACKLIST_KEY = "token:blacklist:{}"


async def get_admin_by_id(session: AsyncSession, admin_id: int) -> Admin | None:
    return await session.get(Admin, admin_id)


async def authenticate_admin(session: AsyncSession, username: str, password: str) -> Admin:
    """Verify credentials; returns the Admin or raises UnauthorizedError."""
    result = await session.execute(select(Admin).where(Admin.username == username))
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active or not verify_password(password, admin.password_hash):
        raise UnauthorizedError("Invalid username or password")
    return admin


def build_token_pair(admin: Admin) -> dict[str, str]:
    access = create_access_token(str(admin.id))
    refresh, _ = create_refresh_token(str(admin.id))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def _jti_ttl_seconds(payload: dict[str, Any]) -> int:
    """Remaining life of a token in seconds, min 1 (PyJWT decodes exp to int)."""
    exp = int(payload["exp"])
    now = int(datetime.now(UTC).timestamp())
    return max(exp - now, 1)


async def _revoke_jti(jti: str, ttl_seconds: int) -> None:
    redis = get_redis()
    try:
        await redis.set(BLACKLIST_KEY.format(jti), "1", ex=ttl_seconds)
    finally:
        await redis.aclose()


async def _is_blacklisted(jti: str) -> bool:
    redis = get_redis()
    try:
        return await redis.exists(BLACKLIST_KEY.format(jti)) == 1
    finally:
        await redis.aclose()


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> dict[str, str]:
    """Validate a refresh token, rotate it (blacklist the old jti), return a new pair."""
    payload = decode_token(refresh_token, expected_type="refresh")
    jti = str(payload["jti"])
    if await _is_blacklisted(jti):
        raise UnauthorizedError("Refresh token revoked")
    admin = await get_admin_by_id(session, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise UnauthorizedError("Admin no longer active")
    await _revoke_jti(jti, _jti_ttl_seconds(payload))
    return build_token_pair(admin)


async def logout(refresh_token: str) -> None:
    """Blacklist the refresh token's jti for its remaining lifetime."""
    payload = decode_token(refresh_token, expected_type="refresh")
    await _revoke_jti(str(payload["jti"]), _jti_ttl_seconds(payload))
