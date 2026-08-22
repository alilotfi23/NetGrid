"""Data-cap usage endpoints: per-subscriber consumption vs plan quota.

Permission: usage:read for the current-month report (read-only; the data
comes from FreeRADIUS's radacct table via the usage service).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.usage import UsageReport, UsageReportItem, UsageStats
from app.services import usage as usage_service

router = APIRouter(prefix="/usage", tags=["usage"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=UsageReport)
@limiter.limit(LIMITS["usage_read"])
async def get_usage_report(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("usage:read"))],
) -> UsageReport:
    """GET /api/v1/usage — requires usage:read.

    Current-month consumption vs plan quota for every plan-assigned
    subscriber (zero-usage subscribers included, ordered by username), plus a
    rollup (total consumed GB, over-quota count) for the dashboard card.
    """
    rows = await usage_service.get_usage_report(session)
    items = [UsageReportItem(**row.to_dict()) for row in rows]
    return UsageReport(
        items=items,
        total=len(items),
        stats=UsageStats(
            total_consumed_gb=round(sum(row.total_gb for row in rows), 2),
            over_quota_count=sum(
                1 for row in rows if row.pct_used is not None and row.pct_used >= 100
            ),
        ),
    )
