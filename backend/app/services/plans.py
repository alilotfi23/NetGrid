"""Plan service: CRUD + direct RADIUS group attribute coupling (Phase 6).

A plan maps 1:1 to a FreeRADIUS group (`radius_group`); the plan's bandwidth
and quota attributes are mirrored into `radgroupreply` rows for that group in
the same transaction as the plan row (CLAUDE.md direct-coupling decision).
`radgroupcheck` is kept empty for now but stays in sync (stale rows are
removed on change). Assigning a subscriber to a plan writes `radusergroup` —
that lives in `app/services/subscribers.py`.

The attribute mapping is deliberate and documented in CLAUDE.md:
  WISPr-Bandwidth-Max-Down/Up    (kbps, integer)   <- bandwidth_down/up_mbps * 1000
  Mikrotik-Total-Limit + Gigawords (64-bit byte pair) <- quota_gb * 1e9 (when set)
The attributes exist in the FreeRADIUS container's shipped dictionaries.
`name` and `radius_group` are immutable after creation (they are the plan's
identity in our schema and in RADIUS); rename = recreate.
"""

from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.plan import Plan
from app.models.radius import RadGroupCheck, RadGroupReply
from app.models.subscriber import Subscriber
from app.services import audit as audit_service

RAD_DOWN_ATTR = "WISPr-Bandwidth-Max-Down"
RAD_UP_ATTR = "WISPr-Bandwidth-Max-Up"
RAD_QUOTA_LIMIT_ATTR = "Mikrotik-Total-Limit"
RAD_QUOTA_GIGAWORDS_ATTR = "Mikrotik-Total-Limit-Gigawords"
RAD_OP_SET = "="
KBPS_PER_MBPS = 1000
BYTES_PER_GB = 1_000_000_000
_32BIT = 2**32


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_plans(
    session: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[Plan], int]:
    """Paginated plan list; `q` matches the plan name (case-insensitive)."""
    count_stmt = select(func.count()).select_from(Plan)
    stmt = select(Plan).order_by(Plan.id)
    if q:
        clause = Plan.name.ilike(f"%{q}%")
        count_stmt = count_stmt.where(clause)
        stmt = stmt.where(clause)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return list(result.scalars().all()), int(total)


async def get_plan_or_404(session: AsyncSession, plan_id: int) -> Plan:
    plan = (await session.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
    if plan is None:
        raise NotFoundError("Plan not found")
    return plan


async def get_subscriber_counts(session: AsyncSession) -> dict[int, int]:
    """Count subscribers per plan (plan_id -> count), for the plans list.

    Plans with no subscribers are absent from the result — callers default
    to 0. One grouped query over subscribers.plan_id.
    """
    rows = (
        await session.execute(
            select(Subscriber.plan_id, func.count())
            .where(Subscriber.plan_id.is_not(None))
            .group_by(Subscriber.plan_id)
        )
    ).all()
    return {plan_id: int(count) for plan_id, count in rows}


# ---------------------------------------------------------------------------
# RADIUS group sync
# ---------------------------------------------------------------------------


def _group_replies(plan: Plan) -> list[RadGroupReply]:
    """The radgroupreply rows a plan's group should carry.

    Quota is written as the Mikrotik 64-bit pair (Total-Limit = low 32 bits,
    Total-Limit-Gigawords = high 32 bits) because a 32-bit octet counter
    overflows at ~4 GiB — a 100 GB quota would wrap. Verified live: the pair
    round-trips through FreeRADIUS into Access-Accept.
    """
    replies = [
        RadGroupReply(
            groupname=plan.radius_group,
            attribute=RAD_DOWN_ATTR,
            op=RAD_OP_SET,
            value=str(plan.bandwidth_down_mbps * KBPS_PER_MBPS),
        ),
        RadGroupReply(
            groupname=plan.radius_group,
            attribute=RAD_UP_ATTR,
            op=RAD_OP_SET,
            value=str(plan.bandwidth_up_mbps * KBPS_PER_MBPS),
        ),
    ]
    if plan.quota_gb is not None:
        quota_bytes = plan.quota_gb * BYTES_PER_GB
        replies.append(
            RadGroupReply(
                groupname=plan.radius_group,
                attribute=RAD_QUOTA_LIMIT_ATTR,
                op=RAD_OP_SET,
                value=str(quota_bytes % _32BIT),
            )
        )
        replies.append(
            RadGroupReply(
                groupname=plan.radius_group,
                attribute=RAD_QUOTA_GIGAWORDS_ATTR,
                op=RAD_OP_SET,
                value=str(quota_bytes // _32BIT),
            )
        )
    return replies


async def _sync_group_rows(session: AsyncSession, plan: Plan) -> None:
    """Replace the plan group's radgroupcheck/radgroupreply rows with fresh ones."""
    await session.execute(delete(RadGroupCheck).where(RadGroupCheck.groupname == plan.radius_group))
    await session.execute(delete(RadGroupReply).where(RadGroupReply.groupname == plan.radius_group))
    for reply in _group_replies(plan):
        session.add(reply)


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, mapping unique-constraint violations to ConflictError."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(message) from None


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


async def create_plan(
    session: AsyncSession,
    *,
    actor_id: int,
    name: str,
    radius_group: str,
    price: Decimal,
    duration_days: int,
    bandwidth_down_mbps: int,
    bandwidth_up_mbps: int,
    quota_gb: int | None = None,
    description: str | None = None,
    is_active: bool = True,
    enforce_quota: bool = False,
) -> Plan:
    """Create the plan row and its radgroupreply rows in one transaction."""
    plan = Plan(
        name=name,
        radius_group=radius_group,
        price=price,
        duration_days=duration_days,
        bandwidth_down_mbps=bandwidth_down_mbps,
        bandwidth_up_mbps=bandwidth_up_mbps,
        quota_gb=quota_gb,
        description=description,
        is_active=is_active,
        enforce_quota=enforce_quota,
    )
    session.add(plan)
    # no_autoflush: the sync's bulk deletes would otherwise flush the pending
    # plan INSERT early, letting a duplicate-name IntegrityError escape the
    # _commit_or_conflict mapping below.
    with session.no_autoflush:
        await _sync_group_rows(session, plan)
    await _commit_or_conflict(session, "Plan name or radius group already exists")
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="create",
        resource="plans",
        resource_id=str(plan.id),
        metadata_={"name": name, "radius_group": radius_group},
    )
    return plan


async def update_plan(
    session: AsyncSession,
    plan: Plan,
    *,
    actor_id: int,
    price: Decimal | None = None,
    duration_days: int | None = None,
    bandwidth_down_mbps: int | None = None,
    bandwidth_up_mbps: int | None = None,
    quota_gb: int | None = None,
    description: str | None = None,
    is_active: bool | None = None,
    enforce_quota: bool | None = None,
) -> Plan:
    """Apply plan changes; bandwidth/quota changes re-sync the RADIUS group rows."""
    changed: list[str] = []
    if price is not None and price != plan.price:
        plan.price = price
        changed.append("price")
    if duration_days is not None and duration_days != plan.duration_days:
        plan.duration_days = duration_days
        changed.append("duration_days")
    if bandwidth_down_mbps is not None and bandwidth_down_mbps != plan.bandwidth_down_mbps:
        plan.bandwidth_down_mbps = bandwidth_down_mbps
        changed.append("bandwidth_down_mbps")
    if bandwidth_up_mbps is not None and bandwidth_up_mbps != plan.bandwidth_up_mbps:
        plan.bandwidth_up_mbps = bandwidth_up_mbps
        changed.append("bandwidth_up_mbps")
    if quota_gb is not None and quota_gb != plan.quota_gb:
        plan.quota_gb = quota_gb
        changed.append("quota_gb")
    if description is not None and description != plan.description:
        plan.description = description
        changed.append("description")
    if is_active is not None and is_active != plan.is_active:
        plan.is_active = is_active
        changed.append("is_active")
    if enforce_quota is not None and enforce_quota != plan.enforce_quota:
        plan.enforce_quota = enforce_quota
        changed.append("enforce_quota")

    if changed:
        with session.no_autoflush:
            await _sync_group_rows(session, plan)
        await _commit_or_conflict(session, "Plan name or radius group already exists")
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="plans",
            resource_id=str(plan.id),
            metadata_={"name": plan.name, "fields": changed},
        )
    return plan
