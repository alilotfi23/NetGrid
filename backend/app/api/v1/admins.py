"""Admin management endpoints (Phase 3 remainder).

Permissions: admins:read for listing, admins:manage for create/update and
role assignment. Every role/permission change invalidates the affected
admin's permission cache, so revocation takes effect immediately.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.pagination import Page
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.admins import AdminCreate, AdminOut, AdminRolesUpdate, AdminUpdate
from app.services import admins as admins_service

router = APIRouter(prefix="/admins", tags=["admins"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=Page[AdminOut])
@limiter.limit(LIMITS["admin_read"])
async def list_admins(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("admins:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[AdminOut]:
    """GET /api/v1/admins — requires admins:read."""
    items, total = await admins_service.list_admins(session, page, page_size)
    return Page(
        items=[AdminOut.model_validate(admin) for admin in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=AdminOut, status_code=201)
@limiter.limit(LIMITS["admin_write"])
async def create_admin(
    request: Request,
    response: Response,
    payload: AdminCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("admins:manage"))],
) -> AdminOut:
    """POST /api/v1/admins — requires admins:manage."""
    admin = await admins_service.create_admin(session, actor_id=actor.id, **payload.model_dump())
    return AdminOut.model_validate(admin)


@router.patch("/{admin_id}", response_model=AdminOut)
@limiter.limit(LIMITS["admin_write"])
async def update_admin(
    request: Request,
    response: Response,
    admin_id: int,
    payload: AdminUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("admins:manage"))],
) -> AdminOut:
    """PATCH /api/v1/admins/{id} — requires admins:manage.

    Only the fields present in the request body are changed. Deactivating
    yourself is rejected (self-protection).
    """
    admin = await admins_service.get_admin_or_404(session, admin_id)
    admin = await admins_service.update_admin(
        session, admin, actor_id=actor.id, **payload.model_dump(exclude_unset=True)
    )
    return AdminOut.model_validate(admin)


@router.put("/{admin_id}/roles", response_model=AdminOut)
@limiter.limit(LIMITS["admin_write"])
async def set_admin_roles(
    request: Request,
    response: Response,
    admin_id: int,
    payload: AdminRolesUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("admins:manage"))],
) -> AdminOut:
    """PUT /api/v1/admins/{id}/roles — requires admins:manage.

    Replaces the admin's full role set. Changing your own roles is rejected
    (self-protection). The admin's permission cache is invalidated, so the
    next request reflects the new permission set.
    """
    admin = await admins_service.get_admin_or_404(session, admin_id)
    admin = await admins_service.set_admin_roles(session, admin, payload.role_ids, actor.id)
    return AdminOut.model_validate(admin)
