"""Subscriber management endpoints (Phase 5).

Permissions: subscribers:read for listing/reading, subscribers:write for
create/update, subscribers:delete for removal. Credential and status changes
write radcheck in the same transaction as the profile row (direct coupling).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.pagination import Page
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.subscribers import (
    SubscriberCreate,
    SubscriberOut,
    SubscriberStats,
    SubscriberUpdate,
)
from app.services import subscribers as subscribers_service

router = APIRouter(prefix="/subscribers", tags=["subscribers"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# Route order matters: this static path must stay ahead of the
# `/{subscriber_id}` routes so "stats" is never parsed as an int id.
@router.get("/stats", response_model=SubscriberStats)
@limiter.limit(LIMITS["subscriber_read"])
async def subscriber_stats(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("subscribers:read"))],
) -> SubscriberStats:
    """GET /api/v1/subscribers/stats — requires subscribers:read.

    Returns active/suspended/expired counts for the dashboard.
    """
    return SubscriberStats(**await subscribers_service.get_subscriber_stats(session))


@router.get("", response_model=Page[SubscriberOut])
@limiter.limit(LIMITS["subscriber_read"])
async def list_subscribers(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("subscribers:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=64),
) -> Page[SubscriberOut]:
    """GET /api/v1/subscribers — requires subscribers:read."""
    items, total = await subscribers_service.list_subscribers(session, page, page_size, q)
    return Page(
        items=[SubscriberOut.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SubscriberOut, status_code=201)
@limiter.limit(LIMITS["subscriber_write"])
async def create_subscriber(
    request: Request,
    response: Response,
    payload: SubscriberCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("subscribers:write"))],
) -> SubscriberOut:
    """POST /api/v1/subscribers — requires subscribers:write."""
    subscriber = await subscribers_service.create_subscriber(
        session, actor_id=actor.id, **payload.model_dump()
    )
    return SubscriberOut.model_validate(subscriber)


@router.get("/{subscriber_id}", response_model=SubscriberOut)
@limiter.limit(LIMITS["subscriber_read"])
async def get_subscriber(
    request: Request,
    response: Response,
    subscriber_id: int,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("subscribers:read"))],
) -> SubscriberOut:
    """GET /api/v1/subscribers/{id} — requires subscribers:read."""
    subscriber = await subscribers_service.get_subscriber_or_404(session, subscriber_id)
    return SubscriberOut.model_validate(subscriber)


@router.patch("/{subscriber_id}", response_model=SubscriberOut)
@limiter.limit(LIMITS["subscriber_write"])
async def update_subscriber(
    request: Request,
    response: Response,
    subscriber_id: int,
    payload: SubscriberUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("subscribers:write"))],
) -> SubscriberOut:
    """PATCH /api/v1/subscribers/{id} — requires subscribers:write.

    Changing the password updates the radcheck Cleartext-Password row;
    changing the status adds/removes the radcheck Auth-Type := Reject row.
    """
    subscriber = await subscribers_service.get_subscriber_or_404(session, subscriber_id)
    subscriber = await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, **payload.model_dump(exclude_unset=True)
    )
    return SubscriberOut.model_validate(subscriber)


@router.delete("/{subscriber_id}", status_code=204)
@limiter.limit(LIMITS["subscriber_write"])
async def delete_subscriber(
    request: Request,
    response: Response,
    subscriber_id: int,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("subscribers:delete"))],
) -> Response:
    """DELETE /api/v1/subscribers/{id} — requires subscribers:delete.

    Removes the profile and every radcheck row for the username.
    """
    subscriber = await subscribers_service.get_subscriber_or_404(session, subscriber_id)
    await subscribers_service.delete_subscriber(session, subscriber, actor.id)
    return Response(status_code=204)
