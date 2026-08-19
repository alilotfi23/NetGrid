"""Live-session endpoints (Phase 9).

Permissions: sessions:read for the list, sessions:disconnect for the
RFC 5176 Disconnect-Request action (sent directly to the NAS via pyrad).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.sessions import DisconnectResult, SessionList, SessionNasCount, SessionStats
from app.schemas.subscribers import LiveSessionOut
from app.services import disconnect as disconnect_service
from app.services import sessions as sessions_service

router = APIRouter(prefix="/sessions", tags=["sessions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=SessionList)
@limiter.limit(LIMITS["sessions_read"])
async def list_sessions(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("sessions:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=64),
) -> SessionList:
    """GET /api/v1/sessions — requires sessions:read.

    Live (open) radacct sessions, newest first, plus global `stats`
    (total open sessions and a per-NAS breakdown) for the dashboard card.
    """
    items, total = await sessions_service.list_live_sessions(session, page, page_size, q)
    total_count, by_nas = await sessions_service.get_live_session_stats(session)
    return SessionList(
        items=[LiveSessionOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        stats=SessionStats(
            total=total_count,
            by_nas=[
                SessionNasCount(nasipaddress=nas, count=count, nas_shortname=shortname)
                for nas, count, shortname in by_nas
            ],
        ),
    )


@router.post("/{session_id}/disconnect", response_model=DisconnectResult)
@limiter.limit(LIMITS["sessions_disconnect"])
async def disconnect_live_session(
    request: Request,
    response: Response,
    session_id: int,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("sessions:disconnect"))],
) -> DisconnectResult:
    """POST /api/v1/sessions/{id}/disconnect — requires sessions:disconnect.

    Sends an RFC 5176 Disconnect-Request (pyrad) straight to the session's
    NAS on port 3799, signed with the NAS device's shared secret. The NAS
    replies Disconnect-ACK/NAK; the radacct row closes when the NAS later
    sends its Accounting-Stop — FastAPI never writes radacct.
    """
    status = await disconnect_service.disconnect_session(
        session, session_id=session_id, actor_id=actor.id
    )
    return DisconnectResult(status=status)
