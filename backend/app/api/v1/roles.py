"""Role and permission management endpoints (Phase 3 remainder).

Permissions: roles:read for listing, roles:manage for create/update and
permission assignment. Editing a role's permissions invalidates the cache
of every admin holding that role, so revocation takes effect immediately.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.pagination import Page
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.admins import (
    PermissionOut,
    RoleCreate,
    RoleOut,
    RolePermissionsUpdate,
    RoleUpdate,
)
from app.services import admins as admins_service

router = APIRouter(prefix="/roles", tags=["roles"])
permissions_router = APIRouter(prefix="/permissions", tags=["permissions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=Page[RoleOut])
@limiter.limit(LIMITS["admin_read"])
async def list_roles(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("roles:read"))],
) -> Page[RoleOut]:
    """GET /api/v1/roles — requires roles:read."""
    roles = await admins_service.list_roles(session)
    return Page(
        items=[RoleOut.model_validate(role) for role in roles],
        total=len(roles),
        page=1,
        page_size=len(roles) or 1,
    )


@router.post("", response_model=RoleOut, status_code=201)
@limiter.limit(LIMITS["admin_write"])
async def create_role(
    request: Request,
    response: Response,
    payload: RoleCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("roles:manage"))],
) -> RoleOut:
    """POST /api/v1/roles — requires roles:manage."""
    role = await admins_service.create_role(session, actor_id=actor.id, **payload.model_dump())
    return RoleOut.model_validate(role)


@router.patch("/{role_id}", response_model=RoleOut)
@limiter.limit(LIMITS["admin_write"])
async def update_role(
    request: Request,
    response: Response,
    role_id: int,
    payload: RoleUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("roles:manage"))],
) -> RoleOut:
    """PATCH /api/v1/roles/{id} — requires roles:manage.

    Renames a role or updates its description. Permission changes go through
    PUT /roles/{id}/permissions instead (they invalidate member caches).
    """
    role = await admins_service.get_role_or_404(session, role_id)
    role = await admins_service.update_role(
        session, role, actor_id=actor.id, **payload.model_dump(exclude_unset=True)
    )
    return RoleOut.model_validate(role)


@router.put("/{role_id}/permissions", response_model=RoleOut)
@limiter.limit(LIMITS["admin_write"])
async def set_role_permissions(
    request: Request,
    response: Response,
    role_id: int,
    payload: RolePermissionsUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("roles:manage"))],
) -> RoleOut:
    """PUT /api/v1/roles/{id}/permissions — requires roles:manage.

    Replaces the role's full permission set and invalidates the cache of every
    admin holding the role. Rejected if the change would strip your own
    admins:manage access (self-protection).
    """
    role = await admins_service.get_role_or_404(session, role_id)
    role = await admins_service.set_role_permissions(
        session, role, payload.permission_codes, actor.id
    )
    return RoleOut.model_validate(role)


@router.delete("/{role_id}", status_code=204)
@limiter.limit(LIMITS["admin_write"])
async def delete_role(
    request: Request,
    response: Response,
    role_id: int,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("roles:manage"))],
) -> Response:
    """DELETE /api/v1/roles/{id} — requires roles:manage.

    Deletes the role, unassigning every member via the admin_roles FK cascade
    and invalidating their permission caches. Rejected if deleting a role you
    hold would strip your own admins:manage access (self-protection).
    """
    role = await admins_service.get_role_or_404(session, role_id)
    await admins_service.delete_role(session, role, actor.id)
    return Response(status_code=204)


@permissions_router.get("", response_model=Page[PermissionOut])
@limiter.limit(LIMITS["admin_read"])
async def list_permissions(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("roles:read"))],
) -> Page[PermissionOut]:
    """GET /api/v1/permissions — requires roles:read.

    The permission catalog, for role-assignment UIs.
    """
    permissions = await admins_service.list_permissions(session)
    return Page(
        items=[PermissionOut.model_validate(permission) for permission in permissions],
        total=len(permissions),
        page=1,
        page_size=len(permissions) or 1,
    )
