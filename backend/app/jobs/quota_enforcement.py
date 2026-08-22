"""Over-quota enforcement job (data-cap lifecycle, post-Phase-13 milestone).

An APScheduler interval job that makes the usage data actionable: it polls
the current-month usage report and disconnects the live sessions of every
subscriber whose consumption has hit their plan quota, using the same pyrad
RFC 5176 Disconnect-Request path as the sessions API (direct coupling —
nothing here writes radacct; the NAS closes the session with its own
Accounting-Stop).

Enforcement is deliberately opt-in and bounded:

- Only plans with ``enforce_quota`` set are considered (the toggle lives on
  the plan; a quota cap alone never disconnects anyone).
- A per-subscriber cooldown (``quota_enforce_cooldown_minutes``) skips a
  breach the job already acted on, so a NAS that never sent Accounting-Stop
  isn't hammered every interval.
- Subscribers over quota but with no *live* session are skipped silently —
  the report still flags them, but there is nothing to disconnect.

Every enforced subscriber gets one ``quota_enforced`` audit entry (resource
``subscribers``) summarizing the run: usage vs quota plus per-session
outcomes. The per-session ``disconnect`` entries already written by
disconnect_service carry the transport-level result (ack/nak/timeout).
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.models.audit import AuditLog
from app.models.radius import RadAcct
from app.services import audit as audit_service
from app.services import disconnect as disconnect_service
from app.services import usage as usage_service

logger = logging.getLogger(__name__)

JOB_ID_QUOTA_ENFORCEMENT = "quota-enforcement"

QUOTA_ENFORCED_ACTION = "quota_enforced"
QUOTA_ENFORCED_RESOURCE = "subscribers"


@dataclass(frozen=True)
class QuotaEnforcementSummary:
    """One run's outcome, for logging and tests."""

    checked: int  # plan-assigned subscribers in the usage report
    over_quota: int  # at/over quota on an enforcement-enabled plan
    skipped_cooldown: int  # over quota but enforced within the cooldown window
    skipped_no_sessions: int  # over quota but no live session to disconnect
    enforced: int  # subscribers we attempted to disconnect
    sessions_disconnected: int  # Disconnect-ACKs received
    sessions_failed: int  # sessions whose disconnect raised

    def to_dict(self) -> dict[str, int]:
        return {
            "checked": self.checked,
            "over_quota": self.over_quota,
            "skipped_cooldown": self.skipped_cooldown,
            "skipped_no_sessions": self.skipped_no_sessions,
            "enforced": self.enforced,
            "sessions_disconnected": self.sessions_disconnected,
            "sessions_failed": self.sessions_failed,
        }


async def _live_sessions(session: AsyncSession, username: str) -> list[RadAcct]:
    """Open (acctstoptime IS NULL) radacct rows for one username, oldest first."""
    result = await session.execute(
        select(RadAcct)
        .where(RadAcct.username == username, RadAcct.acctstoptime.is_(None))
        .order_by(RadAcct.acctstarttime)
    )
    return list(result.scalars().all())


async def _recently_enforced(session: AsyncSession, username: str, cooldown: timedelta) -> bool:
    """True when a quota_enforced entry exists for this username in the cooldown window.

    The cooldown is keyed on the audit trail the job itself writes, so it
    survives restarts and is visible to operators.
    """
    # audit_log.created_at is a timezone-naive TIMESTAMP storing UTC (server
    # now()); compare against a naive UTC cutoff so asyncpg accepts the param.
    cutoff = (datetime.now(UTC) - cooldown).replace(tzinfo=None)
    count = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == QUOTA_ENFORCED_ACTION,
                AuditLog.metadata_["username"].astext == username,
                AuditLog.created_at >= cutoff,
            )
        )
    ).scalar_one()
    return int(count) > 0


async def run_quota_enforcement(session: AsyncSession) -> QuotaEnforcementSummary:
    """Disconnect live sessions of subscribers at/over quota on enforced plans."""
    cooldown = timedelta(minutes=get_settings().quota_enforce_cooldown_minutes)
    report = await usage_service.get_usage_report(session)
    candidates = [
        row
        for row in report
        if row.enforce_quota and row.pct_used is not None and row.pct_used >= 100
    ]
    summary = QuotaEnforcementSummary(
        checked=len(report),
        over_quota=len(candidates),
        skipped_cooldown=0,
        skipped_no_sessions=0,
        enforced=0,
        sessions_disconnected=0,
        sessions_failed=0,
    )

    for row in candidates:
        if await _recently_enforced(session, row.username, cooldown):
            summary = replace(summary, skipped_cooldown=summary.skipped_cooldown + 1)
            continue
        sessions = await _live_sessions(session, row.username)
        if not sessions:
            summary = replace(summary, skipped_no_sessions=summary.skipped_no_sessions + 1)
            continue

        acked = 0
        failed = 0
        for radrow in sessions:
            try:
                # One session may fail (no NAS registered, timeout, NAK) without
                # aborting the sweep — record it and keep going.
                await disconnect_service.disconnect_session(
                    session, session_id=radrow.id, actor_id=None
                )
                acked += 1
            except Exception:
                failed += 1

        summary = replace(
            summary,
            enforced=summary.enforced + 1,
            sessions_disconnected=summary.sessions_disconnected + acked,
            sessions_failed=summary.sessions_failed + failed,
        )
        await audit_service.record_audit(
            session,
            admin_id=None,
            action=QUOTA_ENFORCED_ACTION,
            resource=QUOTA_ENFORCED_RESOURCE,
            resource_id=str(row.subscriber_id),
            metadata_={
                "username": row.username,
                "subscriber_id": row.subscriber_id,
                "quota_gb": row.quota_gb,
                "total_gb": row.total_gb,
                "pct_used": row.pct_used,
                "sessions_attempted": len(sessions),
                "sessions_disconnected": acked,
                "sessions_failed": failed,
            },
        )
    logger.info("quota enforcement: %s", summary.to_dict())
    return summary


async def _quota_enforcement_body() -> None:
    async for session in _sessions():
        await run_quota_enforcement(session)


async def _sessions() -> AsyncIterator[AsyncSession]:
    """Yield one DB session for the job (get_session is an async generator)."""
    async for session in get_session():
        yield session
