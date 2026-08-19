"""NAS device management endpoints (Phase 7).

Permissions: nas_devices:read for listing/reading, nas_devices:write for
create/update/delete. Every mutation mirrors the FreeRADIUS nas table in the
same transaction (direct coupling); shared secrets are Fernet-encrypted at
rest and never appear in responses.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.pagination import Page
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.nas_devices import NasDeviceCreate, NasDeviceOut, NasDeviceUpdate
from app.services import nas_devices as nas_devices_service

router = APIRouter(prefix="/nas-devices", tags=["nas-devices"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=Page[NasDeviceOut])
@limiter.limit(LIMITS["nas_read"])
async def list_nas_devices(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("nas_devices:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=64),
) -> Page[NasDeviceOut]:
    """GET /api/v1/nas-devices — requires nas_devices:read."""
    items, total = await nas_devices_service.list_nas_devices(session, page, page_size, q)
    return Page(
        items=[NasDeviceOut.model_validate(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=NasDeviceOut, status_code=201)
@limiter.limit(LIMITS["nas_write"])
async def create_nas_device(
    request: Request,
    response: Response,
    payload: NasDeviceCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("nas_devices:write"))],
) -> NasDeviceOut:
    """POST /api/v1/nas-devices — requires nas_devices:write."""
    device = await nas_devices_service.create_nas_device(
        session, actor_id=actor.id, **payload.model_dump()
    )
    return NasDeviceOut.model_validate(device)


@router.get("/{nas_device_id}", response_model=NasDeviceOut)
@limiter.limit(LIMITS["nas_read"])
async def get_nas_device(
    request: Request,
    response: Response,
    nas_device_id: int,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("nas_devices:read"))],
) -> NasDeviceOut:
    """GET /api/v1/nas-devices/{id} — requires nas_devices:read."""
    device = await nas_devices_service.get_nas_device_or_404(session, nas_device_id)
    return NasDeviceOut.model_validate(device)


@router.patch("/{nas_device_id}", response_model=NasDeviceOut)
@limiter.limit(LIMITS["nas_write"])
async def update_nas_device(
    request: Request,
    response: Response,
    nas_device_id: int,
    payload: NasDeviceUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("nas_devices:write"))],
) -> NasDeviceOut:
    """PATCH /api/v1/nas-devices/{id} — requires nas_devices:write.

    Changing the secret rotates the nas-table secret; deactivating removes
    the nas row (FreeRADIUS rejects unknown NASes), reactivating recreates it.
    ip_address is immutable.
    """
    device = await nas_devices_service.get_nas_device_or_404(session, nas_device_id)
    device = await nas_devices_service.update_nas_device(
        session, device, actor_id=actor.id, **payload.model_dump(exclude_unset=True)
    )
    return NasDeviceOut.model_validate(device)


@router.delete("/{nas_device_id}", status_code=204)
@limiter.limit(LIMITS["nas_write"])
async def delete_nas_device(
    request: Request,
    response: Response,
    nas_device_id: int,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("nas_devices:write"))],
) -> Response:
    """DELETE /api/v1/nas-devices/{id} — requires nas_devices:write.

    Removes the inventory row and the FreeRADIUS nas row.
    """
    device = await nas_devices_service.get_nas_device_or_404(session, nas_device_id)
    await nas_devices_service.delete_nas_device(session, device, actor.id)
    return Response(status_code=204)
