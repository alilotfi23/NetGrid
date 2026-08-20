"""Audit log endpoints (Phase 12 dashboard viewer).

Permissions:
  audit_logs:read — list audit log entries (inherited by super_admin via *:*
                   and auditor via *:read wildcard grants)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.audit import AuditActorOption, AuditLogFilters, AuditLogList, AuditLogOut
from app.services import audit as audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=AuditLogList)
@limiter.limit(LIMITS["audit_read"])
async def list_audit_logs(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("audit_logs:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin_id: int | None = Query(None, ge=1),
    action: str | None = Query(None, max_length=64),
    resource: str | None = Query(None, max_length=64),
) -> AuditLogList:
    """GET /api/v1/audit-logs — requires audit_logs:read.

    Paginated audit trail, newest first, with the actor's username joined in.
    `admin_id` filters to one actor, `action` to a single action, `resource`
    to a single resource. The response carries the distinct actions/resources
    and admin actors present in the log so the dashboard can build its filter
    dropdowns server-side.
    """
    items, total = await audit_service.list_audit_logs(
        session, page, page_size, admin_id=admin_id, action=action, resource=resource
    )
    usernames = await audit_service.get_admin_usernames(
        session, [entry.admin_id for entry in items if entry.admin_id is not None]
    )
    items_out = []
    for entry in items:
        out = AuditLogOut.model_validate(entry)
        out.admin_username = usernames.get(entry.admin_id) if entry.admin_id is not None else None
        items_out.append(out)
    options = await audit_service.get_audit_log_filter_options(session)
    return AuditLogList(
        items=items_out,
        total=total,
        page=page,
        page_size=page_size,
        filters=AuditLogFilters(
            actions=options["actions"],
            resources=options["resources"],
            admins=[
                AuditActorOption(id=admin_id, username=username)
                for admin_id, username in options["admins"]
            ],
        ),
    )
