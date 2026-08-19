"""Subscriber service: profile CRUD + direct RADIUS credential coupling.

Every mutation writes the `subscribers` row and the FreeRADIUS `radcheck`
rows it implies in a single transaction (CLAUDE.md direct-coupling decision):
the password lives only in radcheck as a `Cleartext-Password` check item, and
any status other than `active` adds an `Auth-Type := Reject` check so the
subscriber cannot authenticate. `plan_id` is deliberately not touched here —
plan assignment writes `radusergroup` and arrives with Phase 6.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.radius import RadCheck
from app.models.subscriber import Subscriber
from app.services import audit as audit_service

RAD_PASSWORD_ATTRIBUTE = "Cleartext-Password"
RAD_AUTH_TYPE_ATTRIBUTE = "Auth-Type"
RAD_REJECT_VALUE = "Reject"
RAD_OP_SET = ":="

ACTIVE_STATUS = "active"
SUSPENDED_STATUS = "suspended"
EXPIRED_STATUS = "expired"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_subscribers(
    session: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[Subscriber], int]:
    """Paginated subscriber list; `q` matches username or full name (case-insensitive)."""
    count_stmt = select(func.count()).select_from(Subscriber)
    stmt = select(Subscriber).order_by(Subscriber.id)
    if q:
        like = f"%{q}%"
        clause = or_(Subscriber.username.ilike(like), Subscriber.full_name.ilike(like))
        count_stmt = count_stmt.where(clause)
        stmt = stmt.where(clause)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return list(result.scalars().all()), int(total)


async def get_subscriber_or_404(session: AsyncSession, subscriber_id: int) -> Subscriber:
    subscriber = (
        await session.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    ).scalar_one_or_none()
    if subscriber is None:
        raise NotFoundError("Subscriber not found")
    return subscriber


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_subscriber(
    session: AsyncSession,
    *,
    actor_id: int,
    username: str,
    full_name: str,
    password: str,
    email: str | None = None,
    phone: str | None = None,
    status: str = ACTIVE_STATUS,
    notes: str | None = None,
) -> Subscriber:
    """Create the profile row and its radcheck credential rows in one transaction."""
    subscriber = Subscriber(
        username=username,
        full_name=full_name,
        email=email,
        phone=phone,
        status=status,
        notes=notes,
    )
    session.add(subscriber)
    session.add(
        RadCheck(
            UserName=username,
            Attribute=RAD_PASSWORD_ATTRIBUTE,
            op=RAD_OP_SET,
            Value=password,
        )
    )
    if status != ACTIVE_STATUS:
        session.add(_reject_check(username))
    await _commit_or_conflict(session, "Username already exists")
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="create",
        resource="subscribers",
        resource_id=str(subscriber.id),
        metadata_={"username": username, "status": status},
    )
    return subscriber


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reject_check(username: str) -> RadCheck:
    return RadCheck(
        UserName=username,
        Attribute=RAD_AUTH_TYPE_ATTRIBUTE,
        op=RAD_OP_SET,
        Value=RAD_REJECT_VALUE,
    )


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, mapping unique-constraint violations to ConflictError."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(message) from None
