"""Subscriber business logic (Phase 5).

Full CRUD lands with Phase 5; this module currently holds the status-count
aggregate used by the dashboard stats endpoint. The radcheck coupling helpers
(list/create/update/delete + radcheck sync) will live here per the plan.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscriber import Subscriber

ACTIVE_STATUS = "active"
SUSPENDED_STATUS = "suspended"
EXPIRED_STATUS = "expired"
KNOWN_STATUSES = (ACTIVE_STATUS, SUSPENDED_STATUS, EXPIRED_STATUS)


async def get_subscriber_stats(session: AsyncSession) -> dict[str, int]:
    """Count subscribers per status in a single grouped query.

    Unknown status values (data drift) are not counted toward any named field,
    but do count toward `total`, keeping the snapshot honest.
    """
    rows = (
        await session.execute(select(Subscriber.status, func.count()).group_by(Subscriber.status))
    ).all()
    counts = {status: count for status, count in rows}
    return {
        ACTIVE_STATUS: counts.get(ACTIVE_STATUS, 0),
        SUSPENDED_STATUS: counts.get(SUSPENDED_STATUS, 0),
        EXPIRED_STATUS: counts.get(EXPIRED_STATUS, 0),
        "total": sum(counts.values()),
    }
