"""Unit tests for usage-based overage billing (radacct excess -> surcharge)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.billing import Invoice
from app.models.plan import Plan
from app.models.radius import RadAcct
from app.models.rbac import Admin
from app.models.subscriber import Subscriber
from app.services import billing as billing_service
from app.services.billing import (
    compute_overage_amount,
    generate_overage_invoices,
)


async def _seed_plan(
    session, *, name="Starter", quota_gb=100, overage_price_per_gb=Decimal("0.50")
) -> Plan:
    plan = Plan(
        name=name,
        radius_group=f"grp-{name.lower()}",
        price=Decimal("9.99"),
        duration_days=30,
        bandwidth_down_mbps=100,
        bandwidth_up_mbps=10,
        quota_gb=quota_gb,
        overage_price_per_gb=overage_price_per_gb,
    )
    session.add(plan)
    return plan


async def _seed_subscriber(session, plan: Plan, username: str) -> Subscriber:
    sub = Subscriber(
        username=username,
        full_name=f"{username} Smith",
        status="active",
        plan=plan,  # relationship so the FK resolves at flush
    )
    session.add(sub)
    return sub


def _seed_session(session, username: str, *, in_octets: int, start) -> None:
    session.add(
        RadAcct(
            username=username,
            nasipaddress="192.168.0.10",
            acctstarttime=start,
            acctsessiontime=3600,
            acctinputoctets=in_octets,
            acctoutputoctets=0,
            framedipaddress="10.0.0.5",
        )
    )


async def _invoices(session) -> list[Invoice]:
    return list((await session.execute(select(Invoice).order_by(Invoice.id))).scalars().all())


# --------------------------------------------------------------------------- compute_overage_amount


async def test_compute_overage_amount_bills_fractional_excess():
    # 12.7 GB over a 10 GB cap at $0.50/GB
    assert compute_overage_amount(12.7, 10, Decimal("0.50")) == Decimal("1.35")


async def test_compute_overage_amount_rounds_half_up_to_cents():
    assert compute_overage_amount(1.33, 1, Decimal("0.10")) == Decimal("0.03")


async def test_compute_overage_amount_zero_within_quota():
    assert compute_overage_amount(8.0, 10, Decimal("0.50")) == Decimal("0.00")
    assert compute_overage_amount(10.0, 10, Decimal("0.50")) == Decimal("0.00")


# --------------------------------------------------------------- generate_overage_invoices

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)
JULY_15 = datetime(2026, 7, 15, tzinfo=UTC)


async def test_generates_overage_invoice_for_excess_usage(session):
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)  # 150 GiB
    await session.commit()

    created = await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )

    assert created == 1
    (invoice,) = await _invoices(session)
    assert invoice.kind == "overage"
    assert invoice.plan_name == "Starter"
    assert invoice.period_start == PERIOD_START
    assert invoice.period_end == PERIOD_END
    assert invoice.status == "issued"
    # 50 GiB over the cap at $0.50/GB
    assert invoice.amount == Decimal("25.00")


async def test_skips_subscribers_within_quota(session):
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "light")
    _seed_session(session, "light", in_octets=80 * 1024**3, start=JULY_15)
    await session.commit()

    created = await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )
    assert created == 0
    assert await _invoices(session) == []


async def test_skips_when_plan_has_no_overage_rate(session):
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=None)
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)
    await session.commit()

    created = await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )
    assert created == 0


async def test_skips_when_plan_has_rate_but_no_quota(session):
    plan = await _seed_plan(session, quota_gb=None, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)
    await session.commit()

    created = await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )
    assert created == 0


async def test_idempotent_second_run(session):
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)
    await session.commit()

    assert (
        await generate_overage_invoices(session, period_start=PERIOD_START, period_end=PERIOD_END)
        == 1
    )
    assert (
        await generate_overage_invoices(session, period_start=PERIOD_START, period_end=PERIOD_END)
        == 0
    )
    assert len(await _invoices(session)) == 1


async def test_default_period_is_previous_calendar_month(session):
    plan = await _seed_plan(session, quota_gb=1, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    this_month = date.today().replace(day=1)
    prev_end = this_month - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    _seed_session(
        session,
        "heavy",
        in_octets=2 * 1024**3,
        start=datetime(prev_start.year, prev_start.month, 15, tzinfo=UTC),
    )
    await session.commit()

    created = await generate_overage_invoices(session)

    assert created == 1
    (invoice,) = await _invoices(session)
    assert invoice.period_start == prev_start
    assert invoice.period_end == prev_end
    assert invoice.amount == Decimal("0.50")  # 1 GB over at $0.50


async def test_explicit_period_only_counts_usage_in_window(session):
    plan = await _seed_plan(session, quota_gb=1, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    # usage in June — outside the July window being billed
    _seed_session(session, "heavy", in_octets=2 * 1024**3, start=datetime(2026, 6, 15, tzinfo=UTC))
    await session.commit()

    created = await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )
    assert created == 0


async def test_audit_entry_when_actor_provided(session):
    admin = Admin(
        username="boss",
        email="boss@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    session.add(admin)
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)
    await session.commit()

    await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END, actor_id=admin.id
    )
    (entry,) = (
        (await session.execute(select(AuditLog).where(AuditLog.action == "overage")))
        .scalars()
        .all()
    )
    assert entry.admin_id == admin.id
    assert entry.resource == "invoices"
    assert entry.metadata_ == {
        "created": 1,
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "total_amount": "25.00",
    }


async def test_base_invoice_does_not_block_overage_for_same_period(session):
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)
    await session.commit()
    # base bill already exists for the period
    await billing_service.generate_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )

    created = await generate_overage_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )

    assert created == 1
    kinds = {inv.kind for inv in await _invoices(session)}
    assert kinds == {"base", "overage"}


async def test_overage_invoice_does_not_block_next_base_generation(session):
    plan = await _seed_plan(session, quota_gb=100, overage_price_per_gb=Decimal("0.50"))
    await _seed_subscriber(session, plan, "heavy")
    _seed_session(session, "heavy", in_octets=150 * 1024**3, start=JULY_15)
    await session.commit()
    await generate_overage_invoices(session, period_start=PERIOD_START, period_end=PERIOD_END)

    # the base generation for the same period must still bill — kinds are separate
    created = await billing_service.generate_invoices(
        session, period_start=PERIOD_START, period_end=PERIOD_END
    )

    assert created == 1
    kinds = {inv.kind for inv in await _invoices(session)}
    assert kinds == {"base", "overage"}


async def test_build_scheduler_registers_overage_billing_job():
    """The app scheduler carries the monthly overage-billing cron job."""
    from app.jobs.invoice_generation import build_scheduler

    scheduler = build_scheduler()
    jobs = {job.id: str(job.trigger) for job in scheduler.get_jobs()}
    assert "overage-billing" in jobs
    # runs on the 2nd of each month, a day after base invoice generation
    assert "day='2'" in jobs["overage-billing"]
