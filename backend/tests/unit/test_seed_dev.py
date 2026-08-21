"""Tests for the dev seed script (``backend/scripts/seed_dev.py``).

The seed runs against the same test session fixture as every other service
test; it exercises the real service layer, so these tests also pin the
coupled RADIUS rows the seed is supposed to produce (radcheck,
radusergroup, radgroupreply, nas).
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

# The script lives outside the `app` package; put the backend root on the
# path so `scripts.seed_dev` resolves the same way the CLI does.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.security import hash_password  # noqa: E402
from app.models.audit import AuditLog  # noqa: E402
from app.models.billing import Invoice, Payment  # noqa: E402
from app.models.nas import NasDevice  # noqa: E402
from app.models.plan import Plan  # noqa: E402
from app.models.radius import (  # noqa: E402
    Nas,
    RadAcct,
    RadCheck,
    RadGroupReply,
    RadUserGroup,
)
from app.models.rbac import Admin  # noqa: E402
from app.models.subscriber import Subscriber  # noqa: E402
from scripts.seed_dev import (  # noqa: E402
    NAS_DEVICES,
    PLANS,
    SESSIONS,
    SUBSCRIBERS,
    UNPAID_PER_MONTH,
    seed_dev,
)

ACTIVE_WITH_PLAN = sum(
    1 for _, _, _, _, status, plan, _ in SUBSCRIBERS if status == "active" and plan is not None
)
INVOICE_MONTHS = 12
EXPECTED_INVOICES = INVOICE_MONTHS * ACTIVE_WITH_PLAN
EXPECTED_UNPAID = sum(UNPAID_PER_MONTH.values())
EXPECTED_PAYMENTS = EXPECTED_INVOICES - EXPECTED_UNPAID
# unpaid in past months flip to overdue; the current month's stay issued
EXPECTED_OVERDUE = EXPECTED_UNPAID - UNPAID_PER_MONTH[INVOICE_MONTHS - 1]


async def _make_admin(session) -> int:
    admin = Admin(
        username="seedadmin",
        email="seed@netgrid.local",
        password_hash=hash_password("secret123"),
    )
    session.add(admin)
    await session.commit()
    return admin.id


@pytest.fixture
async def actor_id(session):
    return await _make_admin(session)


async def _count(session, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_seed_dev_creates_full_demo_dataset(session, actor_id):
    counts = await seed_dev(session, actor_id=actor_id)

    # every section ran (nothing was already present in the fresh schema)
    assert counts == {
        "plans": len(PLANS),
        "nas_devices": len(NAS_DEVICES),
        "subscribers": len(SUBSCRIBERS),
        "invoices": EXPECTED_INVOICES,
        "payments": EXPECTED_PAYMENTS,
        "overdue_flips": EXPECTED_OVERDUE,
        "live_sessions": len(SESSIONS),
    }

    # own-schema rows
    assert await _count(session, Plan) == len(PLANS)
    assert await _count(session, NasDevice) == len(NAS_DEVICES)
    assert await _count(session, Subscriber) == len(SUBSCRIBERS)
    assert await _count(session, Invoice) == EXPECTED_INVOICES
    assert await _count(session, Payment) == EXPECTED_PAYMENTS

    # coupled RADIUS rows, written by the services in the same transactions
    non_active = sum(1 for *_, status, _, _ in SUBSCRIBERS if status != "active")
    assert await _count(session, RadCheck) == len(SUBSCRIBERS) + non_active  # + Auth-Type Reject
    cleartext = (
        await session.execute(
            select(func.count())
            .select_from(RadCheck)
            .where(RadCheck.attribute == "Cleartext-Password")
        )
    ).scalar_one()
    assert cleartext == len(SUBSCRIBERS)
    assigned = sum(1 for *_, plan, _ in SUBSCRIBERS if plan is not None)
    assert await _count(session, RadUserGroup) == assigned  # only plan-assigned subscribers
    active_nas = sum(1 for device in NAS_DEVICES if device.get("is_active", True))
    assert await _count(session, Nas) == active_nas  # inactive devices have no nas row
    # group replies: down+up per plan, plus the 2-row quota pair when set
    assert await _count(session, RadGroupReply) == len(PLANS) * 2 + sum(
        2 for plan in PLANS if plan["quota_gb"] is not None
    )


async def test_seed_dev_is_idempotent(session, actor_id):
    await seed_dev(session, actor_id=actor_id)
    second = await seed_dev(session, actor_id=actor_id)

    assert second["plans"] == 0
    assert second["nas_devices"] == 0
    assert second["subscribers"] == 0
    assert second["invoices"] == 0
    assert second["payments"] == 0
    assert second["live_sessions"] == 0
    assert second["overdue_flips"] == 0

    # nothing duplicated
    assert await _count(session, Subscriber) == len(SUBSCRIBERS)
    assert await _count(session, Invoice) == EXPECTED_INVOICES
    assert await _count(session, Payment) == EXPECTED_PAYMENTS
    assert await _count(session, RadAcct) == len(SESSIONS)


async def test_seed_payments_are_spread_across_all_months(session, actor_id):
    await seed_dev(session, actor_id=actor_id)

    rows = (
        await session.execute(
            select(Payment.created_at, Invoice.period_start)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .order_by(Payment.id)
        )
    ).all()
    months = {f"{created:%Y-%m}" for created, _ in rows}
    # revenue trend: one bucket per trailing month
    assert len(months) == INVOICE_MONTHS
    for created, period_start in rows:
        # backdated to the 15th of the invoice's billing month
        assert created.day == 15
        assert (created.year, created.month) == (period_start.year, period_start.month)


async def test_seed_payment_statuses_are_realistic(session, actor_id):
    await seed_dev(session, actor_id=actor_id)

    paid = await _count(session, Payment)
    issued = await _count(session, Invoice)
    assert paid == EXPECTED_PAYMENTS
    # issued invoices minus paid ones == the unpaid subset
    assert issued - paid == EXPECTED_UNPAID


async def test_seed_dev_requires_an_admin(session):
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        await seed_dev(session)


async def test_seed_open_sessions_join_to_nas_shortname(session, actor_id):
    await seed_dev(session, actor_id=actor_id)

    rows = (
        await session.execute(
            select(
                RadAcct.username,
                RadAcct.nasipaddress,
                RadAcct.acctstoptime,
            ).order_by(RadAcct.id)
        )
    ).all()
    assert len(rows) == len(SESSIONS)
    for (username, nas_ip, stop), (expected_user, expected_ip, *_rest) in zip(
        rows, SESSIONS, strict=True
    ):
        assert username == expected_user
        assert str(nas_ip) == expected_ip
        assert stop is None  # every seeded session is live

    # every open session resolves to a known NAS via the nas table join
    nas_names = set((await session.execute(select(Nas.nasname))).scalars().all())
    for _, nas_ip, _ in rows:
        assert str(nas_ip) in nas_names


async def test_seed_audit_trail_records_admin_actions(session, actor_id):
    await seed_dev(session, actor_id=actor_id)

    actions = set((await session.execute(select(AuditLog.action))).scalars().all())
    # creation + billing actions went through the audit log
    assert {"create", "generate", "payment"} <= actions
