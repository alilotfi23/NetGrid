"""Unit tests for the billing service (services/billing) + invoice job (Phase 10)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.jobs.invoice_generation import run_invoice_generation, run_overdue_sweep
from app.models.audit import AuditLog
from app.models.billing import Invoice, Payment
from app.models.plan import Plan
from app.models.rbac import Admin
from app.models.subscriber import Subscriber
from app.services import billing as billing_service

CENT = Decimal("0.01")


# ---------------------------------------------------------------------------
# Proration / pricing (pure functions)
# ---------------------------------------------------------------------------


def test_prorate_full_period_bills_full_price():
    assert billing_service.prorate_amount(Decimal("9.99"), 30, 30) == Decimal("9.99")


def test_prorate_half_period_bills_half():
    assert billing_service.prorate_amount(Decimal("10.00"), 15, 30) == Decimal("5.00")


def test_prorate_rounds_half_up_to_cents():
    # 10.00 * 7 / 30 = 2.3333... -> 2.33
    assert billing_service.prorate_amount(Decimal("10.00"), 7, 30) == Decimal("2.33")
    # 10.00 * 8 / 30 = 2.6666... -> 2.67
    assert billing_service.prorate_amount(Decimal("10.00"), 8, 30) == Decimal("2.67")


def test_prorate_zero_days_bills_nothing():
    assert billing_service.prorate_amount(Decimal("9.99"), 0, 30) == Decimal("0.00")
    assert billing_service.prorate_amount(Decimal("9.99"), -3, 30) == Decimal("0.00")


def test_prorate_invalid_total_days_raises():
    with pytest.raises(ValueError):
        billing_service.prorate_amount(Decimal("9.99"), 15, 0)


def test_compute_invoice_amount_full_period_is_full_price():
    start = date(2026, 3, 1)
    end = date(2026, 3, 30)  # 30 days
    amount = billing_service.compute_invoice_amount(Decimal("9.99"), start, end, 30)
    assert amount == Decimal("9.99")


def test_compute_invoice_amount_partial_period_is_prorated():
    start = date(2026, 3, 16)
    end = date(2026, 3, 30)  # 15 days
    amount = billing_service.compute_invoice_amount(Decimal("10.00"), start, end, 30)
    assert amount == Decimal("5.00")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _seed_actor(session, username="actor") -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    return admin


async def _seed_plan(session, name="Starter", *, price="9.99", duration_days=30) -> Plan:
    plan = Plan(
        name=name,
        radius_group=f"rad_{name.lower()}",
        price=Decimal(price),
        duration_days=duration_days,
        bandwidth_down_mbps=10,
        bandwidth_up_mbps=5,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    return plan


async def _seed_subscriber(session, username, status="active", plan_id=None) -> Subscriber:
    subscriber = Subscriber(username=username, full_name=username, status=status, plan_id=plan_id)
    session.add(subscriber)
    await session.commit()
    return subscriber


async def _invoices(session) -> list[Invoice]:
    return list((await session.execute(select(Invoice).order_by(Invoice.id))).scalars().all())


async def _payments(session, invoice_id: int) -> list[Payment]:
    return list(
        (
            await session.execute(
                select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.id)
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------


async def test_generate_creates_invoice_for_active_subscriber(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)

    created = await billing_service.generate_invoices(session)
    assert created == 1

    invoices = await _invoices(session)
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv.plan_name == "Starter"
    assert inv.amount == Decimal("9.99")
    assert inv.status == "issued"
    # defaults to the current calendar month
    assert inv.period_start == date.today().replace(day=1)
    assert inv.due_at == inv.period_end


async def test_generate_skips_inactive_plan_and_status(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)  # active
    await _seed_subscriber(session, "sue", status="suspended", plan_id=plan.id)
    await _seed_subscriber(session, "no_plan")  # no plan

    created = await billing_service.generate_invoices(session)
    assert created == 1
    assert len(await _invoices(session)) == 1


async def test_generate_skips_deactivated_plan(session):
    plan = await _seed_plan(session)
    plan.is_active = False
    await session.commit()
    await _seed_subscriber(session, "bob", plan_id=plan.id)

    assert await billing_service.generate_invoices(session) == 0


async def test_generate_is_idempotent(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)

    assert await billing_service.generate_invoices(session) == 1
    assert await billing_service.generate_invoices(session) == 0
    assert len(await _invoices(session)) == 1


async def test_generate_respects_explicit_period(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)

    start, end = date(2026, 6, 1), date(2026, 6, 30)
    created = await billing_service.generate_invoices(session, period_start=start, period_end=end)
    assert created == 1
    inv = (await _invoices(session))[0]
    assert inv.period_start == start
    assert inv.period_end == end


async def test_generate_prorates_short_explicit_period(session):
    plan = await _seed_plan(session, price="10.00", duration_days=30)
    await _seed_subscriber(session, "bob", plan_id=plan.id)

    start, end = date(2026, 6, 16), date(2026, 6, 30)  # 15 days
    created = await billing_service.generate_invoices(session, period_start=start, period_end=end)
    assert created == 1
    assert (await _invoices(session))[0].amount == Decimal("5.00")


async def test_generate_rejects_inverted_period(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)
    with pytest.raises(BadRequestError):
        await billing_service.generate_invoices(
            session,
            period_start=date(2026, 6, 30),
            period_end=date(2026, 6, 1),
        )


async def test_generate_audits_when_actor_given(session):
    actor = await _seed_actor(session)
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)

    await billing_service.generate_invoices(session, actor_id=actor.id)
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert any(
        e.action == "generate" and e.resource == "invoices" and e.admin_id == actor.id for e in rows
    )


# ---------------------------------------------------------------------------
# Overdue marking
# ---------------------------------------------------------------------------


async def test_mark_overdue_flips_issued_past_due_only(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)
    await _seed_subscriber(session, "alice", plan_id=plan.id)
    await billing_service.generate_invoices(
        session, period_start=date(2020, 1, 1), period_end=date(2020, 1, 31)
    )
    invoices = await _invoices(session)
    assert len(invoices) == 2
    # one paid invoice from the same era must not flip
    invoices[0].status = "paid"
    await session.commit()

    overdue = await billing_service.mark_overdue_invoices(session)
    assert overdue == 1
    statuses = {inv.status for inv in await _invoices(session)}
    assert statuses == {"paid", "overdue"}


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


async def _issued_invoice(session, amount="9.99") -> Invoice:
    plan = await _seed_plan(session, price=amount)
    await _seed_subscriber(session, "bob", plan_id=plan.id)
    await billing_service.generate_invoices(
        session, period_start=date(2026, 3, 1), period_end=date(2026, 3, 30)
    )
    return (await _invoices(session))[0]


async def test_full_payment_marks_invoice_paid(session):
    actor = await _seed_actor(session)
    inv = await _issued_invoice(session)
    assert inv.status == "issued"

    payment = await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("9.99"), method="cash"
    )
    assert payment.status == "completed"
    assert inv.status == "paid"
    assert inv.paid_at is not None


async def test_partial_payment_leaves_invoice_issued(session):
    actor = await _seed_actor(session)
    inv = await _issued_invoice(session)

    await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("5.00"), method="cash"
    )
    assert inv.status == "issued"
    assert inv.paid_at is None


async def test_cumulative_payments_flip_invoice_to_paid(session):
    actor = await _seed_actor(session)
    inv = await _issued_invoice(session)

    await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("5.00"), method="cash"
    )
    await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("4.99"), method="wallet"
    )
    assert inv.status == "paid"
    assert len(await _payments(session, inv.id)) == 2


async def test_payment_on_paid_invoice_conflicts(session):
    actor = await _seed_actor(session)
    inv = await _issued_invoice(session)
    await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("9.99"), method="cash"
    )
    with pytest.raises(ConflictError):
        await billing_service.record_payment(
            session, inv, actor_id=actor.id, amount=Decimal("1.00"), method="cash"
        )


async def test_payment_writes_audit_entry(session):
    actor = await _seed_actor(session)
    inv = await _issued_invoice(session)
    await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("9.99"), method="cash"
    )
    rows = (await session.execute(select(AuditLog))).scalars().all()
    payment_events = [e for e in rows if e.action == "payment"]
    assert len(payment_events) == 1
    assert payment_events[0].resource == "invoices"
    assert payment_events[0].metadata_["invoice_status"] == "paid"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def test_get_invoice_or_404_loads_payments(session):
    actor = await _seed_actor(session)
    inv = await _issued_invoice(session)
    await billing_service.record_payment(
        session, inv, actor_id=actor.id, amount=Decimal("9.99"), method="cash"
    )

    found = await billing_service.get_invoice_or_404(session, inv.id)
    assert len(found.payments) == 1
    with pytest.raises(NotFoundError):
        await billing_service.get_invoice_or_404(session, 999)


async def test_list_invoices_filters_and_paginates(session):
    plan = await _seed_plan(session)
    bob = await _seed_subscriber(session, "bob", plan_id=plan.id)
    alice = await _seed_subscriber(session, "alice", plan_id=plan.id)
    await billing_service.generate_invoices(
        session, period_start=date(2026, 3, 1), period_end=date(2026, 3, 30)
    )

    all_inv, total = await billing_service.list_invoices(session, page=1, page_size=20)
    assert total == 2
    assert len(all_inv) == 2

    bob_inv, total = await billing_service.list_invoices(
        session, page=1, page_size=20, subscriber_id=bob.id
    )
    assert total == 1
    assert bob_inv[0].subscriber_id == bob.id

    issued, total = await billing_service.list_invoices(
        session, page=1, page_size=20, status="issued"
    )
    assert total == 2
    paid, total = await billing_service.list_invoices(session, page=1, page_size=20, status="paid")
    assert total == 0

    # pagination slices
    page1, total = await billing_service.list_invoices(session, page=1, page_size=1)
    assert len(page1) == 1 and total == 2
    # alice's invoice exists but never appears in bob's filter
    assert alice.id


async def test_get_invoice_stats_counts_and_outstanding(session):
    plan = await _seed_plan(session, price="10.00")
    await _seed_subscriber(session, "bob", plan_id=plan.id)
    await _seed_subscriber(session, "alice", plan_id=plan.id)
    await billing_service.generate_invoices(
        session, period_start=date(2026, 3, 1), period_end=date(2026, 3, 30)
    )
    invoices = await _invoices(session)
    # pay bob's invoice
    actor = await _seed_actor(session)
    await billing_service.record_payment(
        session, invoices[0], actor_id=actor.id, amount=Decimal("10.00"), method="cash"
    )

    stats = await billing_service.get_invoice_stats(session)
    assert stats == {
        "issued": 1,
        "paid": 1,
        "overdue": 0,
        "outstanding_amount": Decimal("10.00"),
    }


async def test_get_invoice_stats_empty(session):
    stats = await billing_service.get_invoice_stats(session)
    assert stats == {
        "issued": 0,
        "paid": 0,
        "overdue": 0,
        "outstanding_amount": Decimal("0.00"),
    }


async def test_get_subscriber_usernames(session):
    bob = await _seed_subscriber(session, "bob")
    await _seed_subscriber(session, "alice")
    names = await billing_service.get_subscriber_usernames(session, [bob.id])
    assert names == {bob.id: "bob"}
    assert await billing_service.get_subscriber_usernames(session, []) == {}


# ---------------------------------------------------------------------------
# Payments report
# ---------------------------------------------------------------------------


async def _seed_payment(
    session, invoice_id: int, amount: str, method: str, *, created_at: datetime, status="completed"
) -> Payment:
    payment = Payment(
        invoice_id=invoice_id,
        amount=Decimal(amount),
        method=method,
        status=status,
        created_at=created_at,
    )
    session.add(payment)
    await session.commit()
    return payment


async def test_payments_report_groups_by_month_and_method(session):
    inv = await _issued_invoice(session, amount="100.00")
    await _seed_payment(session, inv.id, "50.00", "cash", created_at=datetime(2026, 3, 5))
    await _seed_payment(session, inv.id, "25.00", "cash", created_at=datetime(2026, 3, 20))
    await _seed_payment(session, inv.id, "25.00", "wallet", created_at=datetime(2026, 3, 21))
    await _seed_payment(session, inv.id, "30.00", "cash", created_at=datetime(2026, 2, 10))

    report = await billing_service.get_payments_report(session)
    # newest month first, then method asc within a month
    assert report["items"][0]["month"] == "2026-03"
    assert report["items"][0]["method"] == "cash"
    assert report["items"][0]["revenue"] == Decimal("75.00")
    assert report["items"][0]["count"] == 2
    assert report["items"][1] == {
        "month": "2026-03",
        "method": "wallet",
        "revenue": Decimal("25.00"),
        "count": 1,
    }
    assert report["items"][2] == {
        "month": "2026-02",
        "method": "cash",
        "revenue": Decimal("30.00"),
        "count": 1,
    }
    assert report["total_revenue"] == Decimal("130.00")


async def test_payments_report_excludes_non_completed(session):
    inv = await _issued_invoice(session, amount="100.00")
    await _seed_payment(session, inv.id, "50.00", "cash", created_at=datetime(2026, 3, 5))
    await _seed_payment(
        session, inv.id, "20.00", "cash", created_at=datetime(2026, 3, 6), status="pending"
    )
    await _seed_payment(
        session, inv.id, "10.00", "cash", created_at=datetime(2026, 3, 7), status="failed"
    )

    report = await billing_service.get_payments_report(session)
    assert len(report["items"]) == 1
    assert report["items"][0]["revenue"] == Decimal("50.00")
    assert report["total_revenue"] == Decimal("50.00")


async def test_payments_report_year_filter(session):
    inv = await _issued_invoice(session, amount="100.00")
    await _seed_payment(session, inv.id, "40.00", "cash", created_at=datetime(2026, 3, 5))
    await _seed_payment(session, inv.id, "60.00", "cash", created_at=datetime(2025, 12, 31))

    report_2026 = await billing_service.get_payments_report(session, year=2026)
    assert len(report_2026["items"]) == 1
    assert report_2026["items"][0]["month"] == "2026-03"
    assert report_2026["total_revenue"] == Decimal("40.00")

    report_2025 = await billing_service.get_payments_report(session, year=2025)
    assert len(report_2025["items"]) == 1
    assert report_2025["items"][0]["month"] == "2025-12"
    assert report_2025["total_revenue"] == Decimal("60.00")


async def test_payments_report_empty(session):
    report = await billing_service.get_payments_report(session)
    assert report == {"items": [], "total_revenue": Decimal("0.00")}


# ---------------------------------------------------------------------------
# Scheduled job
# ---------------------------------------------------------------------------


async def test_run_invoice_generation_produces_expected_db_state(session):
    """The monthly job body: creates this month's invoices only."""
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)
    # an old invoice from a past period must NOT be touched by generation
    await billing_service.generate_invoices(
        session, period_start=date(2020, 1, 1), period_end=date(2020, 1, 31)
    )

    created = await run_invoice_generation(session)
    assert created == 1
    invoices = await _invoices(session)
    assert len(invoices) == 2
    statuses = {inv.status for inv in invoices}
    # the old invoice stays issued — only the daily sweep flips it
    assert statuses == {"issued"}


async def test_run_overdue_sweep_flips_past_due_invoices(session):
    """The daily job body: marks only issued invoices past due as overdue."""
    plan = await _seed_plan(session)
    await _seed_subscriber(session, "bob", plan_id=plan.id)
    await _seed_subscriber(session, "alice", plan_id=plan.id)
    # one old invoice (past due) and one paid invoice from the same era
    await billing_service.generate_invoices(
        session, period_start=date(2020, 1, 1), period_end=date(2020, 1, 31)
    )
    invoices = await _invoices(session)
    assert len(invoices) == 2
    invoices[0].status = "paid"
    await session.commit()

    marked = await run_overdue_sweep(session)
    assert marked == 1
    statuses = {inv.status for inv in await _invoices(session)}
    assert statuses == {"paid", "overdue"}


async def test_build_scheduler_registers_both_jobs():
    """The scheduler carries both billing jobs with distinct ids."""
    from app.jobs.invoice_generation import build_scheduler

    scheduler = build_scheduler()
    jobs = {job.id: str(job.trigger) for job in scheduler.get_jobs()}
    assert "monthly-invoice-generation" in jobs
    assert "daily-overdue-sweep" in jobs
    # monthly runs on the 1st; the daily sweep runs every day
    assert "day='1'" in jobs["monthly-invoice-generation"]
    assert "day='1'" not in jobs["daily-overdue-sweep"]
