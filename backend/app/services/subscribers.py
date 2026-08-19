"""Subscriber service: profile CRUD + direct RADIUS credential coupling.

Every mutation writes the `subscribers` row and the FreeRADIUS `radcheck`
rows it implies in a single transaction (CLAUDE.md direct-coupling decision):
the password lives only in radcheck as a `Cleartext-Password` check item, and
any status other than `active` adds an `Auth-Type := Reject` check so the
subscriber cannot authenticate. `plan_id` is deliberately not touched here —
plan assignment writes `radusergroup` and arrives with Phase 6.
"""

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.plan import Plan
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
            username=username,
            attribute=RAD_PASSWORD_ATTRIBUTE,
            op=RAD_OP_SET,
            value=password,
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
# Update / delete
# ---------------------------------------------------------------------------


async def _upsert_password(session: AsyncSession, username: str, password: str) -> None:
    """Set (or create) the Cleartext-Password check row for a subscriber."""
    row = (
        await session.execute(
            select(RadCheck).where(
                RadCheck.username == username,
                RadCheck.attribute == RAD_PASSWORD_ATTRIBUTE,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            RadCheck(
                username=username,
                attribute=RAD_PASSWORD_ATTRIBUTE,
                op=RAD_OP_SET,
                value=password,
            )
        )
    else:
        row.value = password


async def _set_reject(session: AsyncSession, username: str, *, reject: bool) -> None:
    """Add or remove the Auth-Type := Reject check row per the subscriber's status."""
    row = (
        await session.execute(
            select(RadCheck).where(
                RadCheck.username == username,
                RadCheck.attribute == RAD_AUTH_TYPE_ATTRIBUTE,
            )
        )
    ).scalar_one_or_none()
    if reject and row is None:
        session.add(_reject_check(username))
    elif not reject and row is not None:
        await session.delete(row)


async def update_subscriber(
    session: AsyncSession,
    subscriber: Subscriber,
    *,
    actor_id: int,
    full_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> Subscriber:
    """Apply profile changes; password and status changes sync radcheck rows."""
    changed: list[str] = []
    if full_name is not None and full_name != subscriber.full_name:
        subscriber.full_name = full_name
        changed.append("full_name")
    if email is not None and email != subscriber.email:
        subscriber.email = email
        changed.append("email")
    if phone is not None and phone != subscriber.phone:
        subscriber.phone = phone
        changed.append("phone")
    if notes is not None and notes != subscriber.notes:
        subscriber.notes = notes
        changed.append("notes")
    if password is not None:
        await _upsert_password(session, subscriber.username, password)
        changed.append("password")
    if status is not None and status != subscriber.status:
        subscriber.status = status
        await _set_reject(session, subscriber.username, reject=status != ACTIVE_STATUS)
        changed.append("status")

    if changed:
        await _commit_or_conflict(session, "Username already exists")
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="subscribers",
            resource_id=str(subscriber.id),
            metadata_={"username": subscriber.username, "fields": changed},
        )
    return subscriber


async def delete_subscriber(session: AsyncSession, subscriber: Subscriber, actor_id: int) -> None:
    """Delete the profile and every radcheck row for its username in one transaction."""
    username = subscriber.username
    subscriber_id = subscriber.id
    await session.execute(delete(RadCheck).where(RadCheck.username == username))
    await session.delete(subscriber)
    await session.commit()
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="delete",
        resource="subscribers",
        resource_id=str(subscriber_id),
        metadata_={"username": username},
    )


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


async def get_subscriber_plan_counts(
    session: AsyncSession,
) -> list[dict[str, str | int | None]]:
    """Count subscribers per plan (all statuses) via a left join.

    Ordered by plan id; subscribers with no plan (plan_id NULL) come last.
    """
    rows = (
        await session.execute(
            select(Plan.id, Plan.name, func.count(Subscriber.id))
            .select_from(Subscriber)
            .outerjoin(Plan, Plan.id == Subscriber.plan_id)
            .group_by(Plan.id, Plan.name)
            .order_by(Plan.id)
        )
    ).all()
    return [
        {"plan_id": plan_id, "plan_name": plan_name, "count": int(count)}
        for plan_id, plan_name, count in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reject_check(username: str) -> RadCheck:
    return RadCheck(
        username=username,
        attribute=RAD_AUTH_TYPE_ATTRIBUTE,
        op=RAD_OP_SET,
        value=RAD_REJECT_VALUE,
    )


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, mapping unique-constraint violations to ConflictError."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(message) from None
