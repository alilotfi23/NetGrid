"""Plan management endpoints (Phase 6).

Permissions: plans:read for listing/reading, plans:write for create/update.
There is no plan delete — decommissioning a plan means deactivating it
(is_active=false); subscribers keep their assignments. Plan attribute
changes re-sync the RADIUS group rows (radgroupreply) in the same
transaction as the plan row (direct coupling).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.pagination import Page
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.plans import PlanCreate, PlanOut, PlanUpdate
from app.services import plans as plans_service

router = APIRouter(prefix="/plans", tags=["plans"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=Page[PlanOut])
@limiter.limit(LIMITS["plan_read"])
async def list_plans(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("plans:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=64),
) -> Page[PlanOut]:
    """GET /api/v1/plans — requires plans:read.

    Each item carries subscriber_count (assigned subscribers per plan) from
    a grouped count — one extra query, so the dashboard table can show how
    many subscribers each plan serves.
    """
    items, total = await plans_service.list_plans(session, page, page_size, q)
    counts = await plans_service.get_subscriber_counts(session)
    items_out = []
    for p in items:
        out = PlanOut.model_validate(p)
        out.subscriber_count = counts.get(p.id, 0)
        items_out.append(out)
    return Page(
        items=items_out,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=PlanOut, status_code=201)
@limiter.limit(LIMITS["plan_write"])
async def create_plan(
    request: Request,
    response: Response,
    payload: PlanCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("plans:write"))],
) -> PlanOut:
    """POST /api/v1/plans — requires plans:write."""
    plan = await plans_service.create_plan(session, actor_id=actor.id, **payload.model_dump())
    return PlanOut.model_validate(plan)


@router.get("/{plan_id}", response_model=PlanOut)
@limiter.limit(LIMITS["plan_read"])
async def get_plan(
    request: Request,
    response: Response,
    plan_id: int,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("plans:read"))],
) -> PlanOut:
    """GET /api/v1/plans/{id} — requires plans:read."""
    plan = await plans_service.get_plan_or_404(session, plan_id)
    counts = await plans_service.get_subscriber_counts(session)
    out = PlanOut.model_validate(plan)
    out.subscriber_count = counts.get(plan.id, 0)
    return out


@router.patch("/{plan_id}", response_model=PlanOut)
@limiter.limit(LIMITS["plan_write"])
async def update_plan(
    request: Request,
    response: Response,
    plan_id: int,
    payload: PlanUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("plans:write"))],
) -> PlanOut:
    """PATCH /api/v1/plans/{id} — requires plans:write.

    Bandwidth/quota changes re-sync the plan group's radgroupreply rows;
    name and radius_group are immutable.
    """
    plan = await plans_service.get_plan_or_404(session, plan_id)
    plan = await plans_service.update_plan(
        session, plan, actor_id=actor.id, **payload.model_dump(exclude_unset=True)
    )
    return PlanOut.model_validate(plan)
