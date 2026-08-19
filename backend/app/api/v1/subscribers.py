"""Subscriber endpoints (Phase 5, partial).

Currently only the dashboard stats aggregate; full CRUD lands with Phase 5.
Permissions: subscribers:read for reads (stats), subscribers:write/delete for
the future mutations.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.subscribers import SubscriberStats
from app.services import subscribers as subscribers_service

router = APIRouter(prefix="/subscribers", tags=["subscribers"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


# Route order matters: this static path must stay ahead of the Phase 5
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
