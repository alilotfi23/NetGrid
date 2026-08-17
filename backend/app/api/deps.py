"""Shared FastAPI dependencies for authenticated endpoints."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.rbac import has_permission
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.models.rbac import Admin
from app.services.audit import record_permission_denied
from app.services.auth import get_admin_by_id
from app.services.rbac import get_permission_state

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentAdmin:
    admin: Admin
    payload: dict[str, Any]  # decoded access-token claims (sub, type, jti, perm_version, ...)


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentAdmin:
    """Resolve the authenticated admin + token claims.

    Authentication only — authorization goes through require_permission(...).
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_token(credentials.credentials, expected_type=TOKEN_TYPE_ACCESS)
    admin = await get_admin_by_id(session, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise UnauthorizedError("Admin no longer active")
    return CurrentAdmin(admin=admin, payload=payload)


def require_permission(permission: str) -> Callable[..., Coroutine[Any, Any, Admin]]:
    """Dependency factory: authentication + permission check.

    Rejects a token whose perm_version no longer matches the admin's current
    permission set (401, forces re-login after any role change) and returns
    403 when the permission is missing. Denials are written to audit_log.
    """

    async def dependency(
        request: Request,
        current: Annotated[CurrentAdmin, Depends(get_current_admin)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> Admin:
        state = await get_permission_state(session, current.admin.id)
        if state.version != current.payload.get("perm_version"):
            raise UnauthorizedError("Permissions changed, please sign in again")
        if not has_permission(state.codes, permission):
            await record_permission_denied(session, current.admin.id, permission, request.url.path)
            raise ForbiddenError()
        return current.admin

    return dependency
