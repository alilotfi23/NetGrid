"""Shared FastAPI dependencies for authenticated endpoints."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import UnauthorizedError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.models.rbac import Admin
from app.services.auth import get_admin_by_id

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Admin:
    """Resolve the authenticated admin from the access token.

    Authentication only — Plan 3 wraps this with require_permission(...) for
    authorization.
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_token(credentials.credentials, expected_type=TOKEN_TYPE_ACCESS)
    admin = await get_admin_by_id(session, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise UnauthorizedError("Admin no longer active")
    return admin
