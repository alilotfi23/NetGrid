"""Subscriber service: profile CRUD + direct RADIUS credential coupling.

Every mutation writes the `subscribers` row and the FreeRADIUS `radcheck`
rows it implies in a single transaction (CLAUDE.md direct-coupling decision):
the password lives only in radcheck as a `Cleartext-Password` check item, and
any status other than `active` adds an `Auth-Type := Reject` check so the
subscriber cannot authenticate. `plan_id` is deliberately not touched here —
plan assignment writes `radusergroup` and arrives with Phase 6.
"""

from typing import cast

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.audit import AuditLog
from app.models.plan import Plan
from app.models.radius import RadAcct, RadCheck, RadUserGroup
from app.models.subscriber import Subscriber
from app.services import audit as audit_service
from app.services import plans as plans_service

# Sentinel distinguishing "plan_id not provided" from "plan_id explicitly
# cleared" (None) in update_subscriber.
_UNSET: object = object()

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
    session: AsyncSession,
    page: int,
    page_size: int,
    q: str | None = None,
    plan_id: int | None = None,
    no_plan: bool = False,
) -> tuple[list[Subscriber], int]:
    """Paginated subscriber list.

    `q` matches username or full name (case-insensitive); `plan_id` filters to
    a specific plan and `no_plan` filters to subscribers with no plan — the
    dashboard's by-plan breakdown drills down through these.
    """
    count_stmt = select(func.count()).select_from(Subscriber)
    stmt = select(Subscriber).order_by(Subscriber.id)
    if q:
        like = f"%{q}%"
        clause = or_(Subscriber.username.ilike(like), Subscriber.full_name.ilike(like))
        count_stmt = count_stmt.where(clause)
        stmt = stmt.where(clause)
    if plan_id is not None:
        count_stmt = count_stmt.where(Subscriber.plan_id == plan_id)
        stmt = stmt.where(Subscriber.plan_id == plan_id)
    if no_plan:
        count_stmt = count_stmt.where(Subscriber.plan_id.is_(None))
        stmt = stmt.where(Subscriber.plan_id.is_(None))
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


async def list_subscriber_history(
    session: AsyncSession, subscriber_id: int, limit: int = 20
) -> list[AuditLog]:
    """Recent audit events for a subscriber (create/update), newest first.

    Status changes carry status_from/status_to in their metadata.
    """
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.resource == "subscribers", AuditLog.resource_id == str(subscriber_id))
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_live_sessions(session: AsyncSession, username: str) -> list[dict[str, object]]:
    """Active radacct sessions (acctstoptime IS NULL) for a username, newest first.

    Inet columns are cast to str for JSON serialization.
    """
    result = await session.execute(
        select(RadAcct)
        .where(RadAcct.username == username, RadAcct.acctstoptime.is_(None))
        .order_by(RadAcct.acctstarttime.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "nasipaddress": str(row.nasipaddress) if row.nasipaddress else None,
            "acctstarttime": row.acctstarttime,
            "acctsessiontime": row.acctsessiontime,
            "acctinputoctets": row.acctinputoctets,
            "acctoutputoctets": row.acctoutputoctets,
            "framedipaddress": str(row.framedipaddress) if row.framedipaddress else None,
        }
        for row in rows
    ]


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
    plan_id: int | None = None,
) -> Subscriber:
    """Create the profile row and its radcheck/radusergroup rows in one transaction."""
    # resolve the plan before adding anything, so an unknown plan_id surfaces
    # as a 404 instead of a foreign-key IntegrityError at flush time
    plan = None
    if plan_id is not None:
        plan = await plans_service.get_plan_or_404(session, plan_id)
    subscriber = Subscriber(
        username=username,
        full_name=full_name,
        email=email,
        phone=phone,
        status=status,
        notes=notes,
        plan_id=plan_id,
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
    if plan is not None:
        session.add(RadUserGroup(username=username, groupname=plan.radius_group, priority=1))
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
    plan_id: int | None | object = _UNSET,
) -> Subscriber:
    """Apply profile changes; password/status/plan changes sync rad* rows.

    `plan_id` is a sentinel field: pass an int to assign/switch plans, None
    to clear the plan, or omit it to leave the assignment untouched.
    """
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
    status_from: str | None = None
    if status is not None and status != subscriber.status:
        status_from = subscriber.status
        subscriber.status = status
        await _set_reject(session, subscriber.username, reject=status != ACTIVE_STATUS)
        changed.append("status")
    plan_from: str | None = None
    plan_to: str | None = None
    if plan_id is not _UNSET and plan_id != subscriber.plan_id:
        if subscriber.plan_id is not None:
            # plans are decommissioned (is_active=false), never deleted, so the
            # previous plan still resolves by id for its name
            old_plan = await plans_service.get_plan_or_404(session, subscriber.plan_id)
            plan_from = old_plan.name
        if plan_id is None:
            subscriber.plan_id = None
            new_group: str | None = None
        else:
            new_plan = await plans_service.get_plan_or_404(session, cast(int, plan_id))
            subscriber.plan_id = new_plan.id
            new_group = new_plan.radius_group
            plan_to = new_plan.name
        # one plan per subscriber: replace any existing membership row
        await session.execute(
            delete(RadUserGroup).where(RadUserGroup.username == subscriber.username)
        )
        if new_group is not None:
            session.add(RadUserGroup(username=subscriber.username, groupname=new_group, priority=1))
        changed.append("plan_id")

    if changed:
        await _commit_or_conflict(session, "Username already exists")
        metadata_: dict[str, object] = {"username": subscriber.username, "fields": changed}
        if "status" in changed:
            metadata_["status_from"] = status_from
            metadata_["status_to"] = subscriber.status
        if "plan_id" in changed:
            metadata_["plan_from"] = plan_from
            metadata_["plan_to"] = plan_to
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="subscribers",
            resource_id=str(subscriber.id),
            metadata_=metadata_,
        )
    return subscriber


async def delete_subscriber(session: AsyncSession, subscriber: Subscriber, actor_id: int) -> None:
    """Delete the profile and its radcheck/radusergroup rows in one transaction."""
    username = subscriber.username
    subscriber_id = subscriber.id
    await session.execute(delete(RadCheck).where(RadCheck.username == username))
    await session.execute(delete(RadUserGroup).where(RadUserGroup.username == username))
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


async def get_subscriber_plan_status_counts(
    session: AsyncSession,
) -> list[dict[str, str | int | None]]:
    """Count subscribers grouped by (plan, status) — the status-by-plan matrix.

    One row per non-empty cell, ordered by plan id (unassigned last) then
    status. The dashboard can pivot this into a stacked per-plan chart.
    """
    rows = (
        await session.execute(
            select(Plan.id, Plan.name, Subscriber.status, func.count(Subscriber.id))
            .select_from(Subscriber)
            .outerjoin(Plan, Plan.id == Subscriber.plan_id)
            .group_by(Plan.id, Plan.name, Subscriber.status)
            .order_by(Plan.id, Subscriber.status)
        )
    ).all()
    return [
        {"plan_id": plan_id, "plan_name": plan_name, "status": status, "count": int(count)}
        for plan_id, plan_name, status, count in rows
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
