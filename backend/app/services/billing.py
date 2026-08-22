"""Billing service: pricing/proration, invoice generation, payments (Phase 10).

The monthly invoice job (`app/jobs/invoice_generation.py`) drives
`generate_invoices`, which bills every active subscriber on an active plan
once per period. Payments accumulate against an invoice; the invoice flips
to ``paid`` only when completed payments reach its amount. Proration applies
when the billed period is shorter than the plan's duration (e.g. a mid-cycle
activation or a partial-month manual run).

Status model:
  Invoice:  issued -> paid | overdue
  Payment:  pending -> completed | failed   (the API only creates completed)

No RADIUS coupling here — billing is pure bookkeeping on our own tables.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.billing import Invoice, Payment
from app.models.plan import Plan
from app.models.subscriber import Subscriber
from app.services import audit as audit_service
from app.services import usage as usage_service

INVOICE_ISSUED = "issued"
INVOICE_PAID = "paid"
INVOICE_OVERDUE = "overdue"
INVOICE_BASE = "base"
INVOICE_OVERAGE = "overage"

PAYMENT_PENDING = "pending"
PAYMENT_COMPLETED = "completed"
PAYMENT_FAILED = "failed"

CENT = Decimal("0.01")


# ---------------------------------------------------------------------------
# Pricing / proration (pure functions, unit-tested directly)
# ---------------------------------------------------------------------------


def prorate_amount(price: Decimal, days_in_period: int, total_days: int) -> Decimal:
    """Pro-rate ``price`` to a partial period, rounded half-up to cents.

    ``days_in_period`` is the number of billed days; ``total_days`` is the
    plan's full period length. A zero/negative billed period bills nothing.
    """
    if total_days <= 0:
        raise ValueError("total_days must be positive")
    if days_in_period <= 0:
        return Decimal("0.00")
    ratio = Decimal(days_in_period) / Decimal(total_days)
    return (price * ratio).quantize(CENT, rounding=ROUND_HALF_UP)


def compute_invoice_amount(
    price: Decimal, period_start: date, period_end: date, duration_days: int
) -> Decimal:
    """Amount for a period: full price when it spans the plan duration, else prorated.

    A period at least as long as the plan's duration bills the full price; a
    shorter period (partial month, mid-cycle activation) is prorated by days.
    """
    period_days = (period_end - period_start).days + 1
    if period_days >= duration_days:
        return price
    return prorate_amount(price, period_days, duration_days)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_invoices(
    session: AsyncSession,
    page: int,
    page_size: int,
    *,
    subscriber_id: int | None = None,
    status: str | None = None,
) -> tuple[list[Invoice], int]:
    """Paginated invoice list, newest first; filters on subscriber/status."""
    count_stmt = select(func.count()).select_from(Invoice)
    stmt = (
        select(Invoice)
        .options(selectinload(Invoice.payments))
        .order_by(Invoice.issued_at.desc(), Invoice.id.desc())
    )
    if subscriber_id is not None:
        count_stmt = count_stmt.where(Invoice.subscriber_id == subscriber_id)
        stmt = stmt.where(Invoice.subscriber_id == subscriber_id)
    if status is not None:
        count_stmt = count_stmt.where(Invoice.status == status)
        stmt = stmt.where(Invoice.status == status)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return list(result.scalars().all()), int(total)


async def get_invoice_or_404(session: AsyncSession, invoice_id: int) -> Invoice:
    """Fetch one invoice with its payments eager-loaded."""
    invoice = (
        await session.execute(
            select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.payments))
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    return invoice


async def get_invoice_stats(session: AsyncSession) -> dict[str, int | Decimal]:
    """Status counts plus the total outstanding (unpaid) amount."""
    rows = (
        await session.execute(select(Invoice.status, func.count()).group_by(Invoice.status))
    ).all()
    counts: dict[str, int] = {INVOICE_ISSUED: 0, INVOICE_PAID: 0, INVOICE_OVERDUE: 0}
    for status, count in rows:
        counts[status] = int(count)
    outstanding = (
        await session.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status.in_([INVOICE_ISSUED, INVOICE_OVERDUE])
            )
        )
    ).scalar_one()
    overdue_amount = (
        await session.execute(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status == INVOICE_OVERDUE
            )
        )
    ).scalar_one()
    # quantize so an empty balance serializes as "0.00", not "0"
    return {
        **counts,
        "outstanding_amount": Decimal(outstanding).quantize(CENT),
        "overdue_amount": Decimal(overdue_amount).quantize(CENT),
    }


async def get_subscriber_usernames(session: AsyncSession, ids: list[int]) -> dict[int, str]:
    """Map subscriber id -> username for the API layer's display fields."""
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Subscriber.id, Subscriber.username).where(Subscriber.id.in_(ids))
        )
    ).all()
    return {sub_id: username for sub_id, username in rows}


# ---------------------------------------------------------------------------
# Invoice generation (job + manual trigger)
# ---------------------------------------------------------------------------


def _month_end(start: date) -> date:
    """Last day of the calendar month containing ``start``."""
    if start.month == 12:
        return date(start.year + 1, 1, 1) - timedelta(days=1)
    return date(start.year, start.month + 1, 1) - timedelta(days=1)


async def generate_invoices(
    session: AsyncSession,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    actor_id: int | None = None,
) -> int:
    """Generate one invoice per active subscriber on an active plan for the period.

    Defaults to the current calendar month. Idempotent: a subscriber who
    already has a *base* invoice whose period overlaps [period_start,
    period_end] is skipped (overage surcharges are a separate kind with
    their own idempotency in generate_overage_invoices), so re-running the
    job never double-bills. Returns the number of invoices created.
    """
    today = date.today()
    start = period_start or today.replace(day=1)
    end = period_end or _month_end(start)
    if end < start:
        raise BadRequestError("period_end must be on or after period_start")

    subscribers = (
        (
            await session.execute(
                select(Subscriber)
                .join(Subscriber.plan)
                .options(contains_eager(Subscriber.plan))
                .where(Subscriber.status == "active", Plan.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )

    created = 0
    for subscriber in subscribers:
        overlap = (
            await session.execute(
                select(func.count())
                .select_from(Invoice)
                .where(
                    Invoice.subscriber_id == subscriber.id,
                    Invoice.kind == INVOICE_BASE,
                    Invoice.period_start <= end,
                    Invoice.period_end >= start,
                )
            )
        ).scalar_one()
        if overlap > 0:
            continue
        plan = subscriber.plan
        # contains_eager guarantees the joined plan is present; the join itself
        # filtered out NULL plan_id, so assert to satisfy mypy's narrowing.
        assert plan is not None
        amount = compute_invoice_amount(plan.price, start, end, plan.duration_days)
        session.add(
            Invoice(
                subscriber_id=subscriber.id,
                plan_name=plan.name,
                kind=INVOICE_BASE,
                period_start=start,
                period_end=end,
                amount=amount,
                status=INVOICE_ISSUED,
                due_at=end,
            )
        )
        created += 1

    await session.commit()
    if actor_id is not None and created:
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="generate",
            resource="invoices",
            metadata_={
                "created": created,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            },
        )
    return created


async def mark_overdue_invoices(session: AsyncSession) -> int:
    """Flip issued invoices whose due date has passed to ``overdue``."""
    result = await session.execute(
        update(Invoice)
        .where(Invoice.status == INVOICE_ISSUED, Invoice.due_at < date.today())
        .values(status=INVOICE_OVERDUE)
    )
    await session.commit()
    # CursorResult.rowcount: how many rows the UPDATE actually changed
    return result.rowcount or 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Usage overage surcharges (usage-based billing)
# ---------------------------------------------------------------------------


def compute_overage_amount(usage_gb: float, quota_gb: int, price_per_gb: Decimal) -> Decimal:
    """Surcharge for ``usage_gb`` on a ``quota_gb`` cap at a per-GB rate.

    Fractional excess is billed fractionally (12.7 GB over at $0.50 = $6.35),
    rounded half-up to cents. Returns 0.00 when usage is within quota.
    """
    excess = Decimal(str(usage_gb)) - Decimal(quota_gb)
    if excess <= 0:
        return Decimal("0.00")
    return (excess * price_per_gb).quantize(CENT, rounding=ROUND_HALF_UP)


async def generate_overage_invoices(
    session: AsyncSession,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    actor_id: int | None = None,
) -> int:
    """Bill per-GB surcharges for usage beyond plan quota in a completed period.

    Defaults to the previous calendar month — the base invoice for the
    current month is generated on the 1st, and by the 2nd the prior month's
    radacct is settled enough to bill. Only plans with both a quota cap and
    an ``overage_price_per_gb`` are considered; excess GB is billed at that
    rate (fractional, half-up to cents). Idempotent per (subscriber, period,
    kind=overage), so re-runs never double-bill; a subscriber's *base*
    invoice for the same period doesn't collide because kinds are separate.
    Returns the number of invoices created.
    """
    if period_start is None or period_end is None:
        # previous calendar month: the month before the current month's first day
        this_month_start = date.today().replace(day=1)
        period_end = this_month_start - timedelta(days=1)
        period_start = period_end.replace(day=1)
    start, end = period_start, period_end
    if end < start:
        raise BadRequestError("period_end must be on or after period_start")

    window_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    window_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    report = await usage_service.get_usage_report(session, start=window_start, end=window_end)

    created = 0
    total_amount = Decimal("0.00")
    for row in report:
        if row.quota_gb is None or row.overage_price_per_gb is None:
            continue
        amount = compute_overage_amount(row.total_gb, row.quota_gb, row.overage_price_per_gb)
        if amount <= 0:
            continue
        already = (
            await session.execute(
                select(func.count())
                .select_from(Invoice)
                .where(
                    Invoice.subscriber_id == row.subscriber_id,
                    Invoice.kind == INVOICE_OVERAGE,
                    Invoice.period_start == start,
                    Invoice.period_end == end,
                )
            )
        ).scalar_one()
        if already > 0:
            continue
        session.add(
            Invoice(
                subscriber_id=row.subscriber_id,
                plan_name=row.plan_name,
                kind=INVOICE_OVERAGE,
                period_start=start,
                period_end=end,
                amount=amount,
                status=INVOICE_ISSUED,
                due_at=end,
            )
        )
        created += 1
        total_amount += amount

    await session.commit()
    if actor_id is not None and created:
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="overage",
            resource="invoices",
            metadata_={
                "created": created,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "total_amount": str(total_amount.quantize(CENT)),
            },
        )
    return created


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


async def record_payment(
    session: AsyncSession,
    invoice: Invoice,
    *,
    actor_id: int,
    amount: Decimal,
    method: str,
    reference: str | None = None,
) -> Payment:
    """Record a completed payment against an invoice.

    The invoice transitions to ``paid`` (with ``paid_at``) the moment
    completed payments reach or exceed its amount; partial payments leave it
    issued. Paying an already-paid invoice is rejected.
    """
    if invoice.status == INVOICE_PAID:
        raise ConflictError("Invoice already paid")

    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        method=method,
        reference=reference,
        status=PAYMENT_COMPLETED,
    )
    session.add(payment)

    paid_total = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.invoice_id == invoice.id,
                Payment.status == PAYMENT_COMPLETED,
            )
        )
    ).scalar_one()
    if Decimal(paid_total) >= invoice.amount:
        invoice.status = INVOICE_PAID
        invoice.paid_at = datetime.now(UTC).replace(tzinfo=None)

    await session.commit()
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="payment",
        resource="invoices",
        resource_id=str(invoice.id),
        metadata_={
            "amount": str(amount),
            "method": method,
            "invoice_status": invoice.status,
        },
    )
    return payment


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


async def get_payments_report(
    session: AsyncSession,
    *,
    year: int | None = None,
) -> dict[str, object]:
    """Revenue grouped by (month, method) for completed payments.

    Returns ``{"items": [{month, method, revenue, count}, ...],
    "total_revenue": Decimal}`` with months newest-first. ``year`` narrows
    to one calendar year (e.g. 2026). Only ``completed`` payments count;
    pending/failed are excluded.
    """
    month_expr = func.to_char(Payment.created_at, "YYYY-MM").label("month")
    stmt = (
        select(
            month_expr,
            Payment.method,
            func.coalesce(func.sum(Payment.amount), 0),
            func.count(),
        )
        .where(Payment.status == PAYMENT_COMPLETED)
        .group_by(month_expr, Payment.method)
        .order_by(month_expr.desc(), Payment.method)
    )
    if year is not None:
        stmt = stmt.where(func.extract("year", Payment.created_at) == year)

    rows = (await session.execute(stmt)).all()
    items: list[dict[str, object]] = []
    total = Decimal("0.00")
    for month, method, revenue, count in rows:
        revenue_dec = Decimal(revenue).quantize(CENT)
        total += revenue_dec
        items.append(
            {
                "month": str(month),
                "method": method,
                "revenue": revenue_dec,
                "count": int(count),
            }
        )
    return {"items": items, "total_revenue": total.quantize(CENT)}
