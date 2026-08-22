"""Seed realistic demo data into a NetGrid database (dev tooling).

Idempotent by section: a section that already has data is skipped, so
re-running against a database that already carries demo data is a no-op
rather than a duplicate. Everything is written through the same services
the API uses, so the data lands in every coupled table (radcheck,
radusergroup, radgroupreply, nas) in the correct transactions, and audit
entries are recorded exactly as real admin actions would be.

What it creates (only when absent):

  * four plans (three active, one decommissioned) with their radgroupreply
    bandwidth/quota rows
  * three NAS devices (two active MikroTik, one inactive Cisco) with their
    FreeRADIUS ``nas`` rows
  * twelve subscribers (active / suspended / expired mix, most with plan
    assignments) with their radcheck credential rows
  * invoices for each of the last 12 months plus the current month, and
    payments spread across those months — backdated to the billing month —
    so the dashboard's 12-month revenue trend renders fully populated
  * overdue flips for past-due unpaid invoices, and open radacct sessions
    for the live-sessions cards

Usage (from the repo root):

    cd backend
    .venv/Scripts/python.exe scripts/seed_dev.py              # dev database
    DATABASE_URL=postgresql+asyncpg://... scripts/seed_dev.py  # other DB

Requires a migrated database (``alembic upgrade head``) so the seeded
``superadmin`` admin exists to act as the audit-log actor, plus the
FreeRADIUS tables (radcheck, radgroupreply, ...): the compose postgres
applies ``freeradius/raddb/mods-config/sql/main/postgresql/schema.sql``
at init, so ``docker compose up postgres`` on a fresh volume is enough —
a host-run database needs that schema applied by hand. Exit code 0 on
success.
"""

import asyncio
import calendar
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Make `app` importable when run as `python scripts/seed_dev.py` from
# anywhere (sys.path[0] is the scripts dir, not the backend root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import ProgrammingError  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings  # noqa: E402
from app.models.billing import Payment  # noqa: E402
from app.models.plan import Plan  # noqa: E402
from app.models.radius import RadAcct  # noqa: E402
from app.models.rbac import Admin  # noqa: E402
from app.services import billing as billing_service  # noqa: E402
from app.services import nas_devices as nas_service  # noqa: E402
from app.services import plans as plans_service  # noqa: E402
from app.services import subscribers as subs_service  # noqa: E402

# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

PLANS: list[dict[str, object]] = [
    {
        "name": "Starter",
        "radius_group": "starter",
        "price": Decimal("9.99"),
        "duration_days": 30,
        "bandwidth_down_mbps": 10,
        "bandwidth_up_mbps": 5,
        "quota_gb": 200,
        "description": "10 Mbps residential plan",
        "enforce_quota": True,
        "overage_price_per_gb": Decimal("0.50"),
    },
    {
        "name": "Pro",
        "radius_group": "pro",
        "price": Decimal("19.99"),
        "duration_days": 30,
        "bandwidth_down_mbps": 25,
        "bandwidth_up_mbps": 10,
        "quota_gb": 500,
        "description": "25 Mbps residential plan",
        "enforce_quota": True,
        "overage_price_per_gb": Decimal("0.50"),
    },
    {
        "name": "Fiber",
        "radius_group": "fiber",
        "price": Decimal("29.99"),
        "duration_days": 30,
        "bandwidth_down_mbps": 50,
        "bandwidth_up_mbps": 20,
        "quota_gb": 1000,
        "description": "50 Mbps fiber plan",
        "enforce_quota": True,
        "overage_price_per_gb": Decimal("0.50"),
    },
    {
        "name": "Legacy ADSL",
        "radius_group": "legacy_adsl",
        "price": Decimal("14.99"),
        "duration_days": 30,
        "bandwidth_down_mbps": 5,
        "bandwidth_up_mbps": 1,
        "quota_gb": None,
        "description": "Decommissioned ADSL product, kept for reference",
        "is_active": False,
    },
]

NAS_DEVICES: list[dict[str, object]] = [
    {
        "name": "Edge Router 1",
        "ip_address": "192.168.0.10",
        "shortname": "edge1",
        "secret": "netgrid_edge1_secret",
        "nas_type": "mikrotik",
        "ports": 1812,
        "server": "radius.netgrid.local",
        "community": "public",
        "description": "Main edge router (MikroTik CCR1036)",
    },
    {
        "name": "Edge Router 2",
        "ip_address": "192.168.0.11",
        "shortname": "edge2",
        "secret": "netgrid_edge2_secret",
        "nas_type": "mikrotik",
        "ports": 1812,
        "server": "radius.netgrid.local",
        "community": "public",
        "description": "Secondary edge router (MikroTik RB4011)",
    },
    {
        "name": "Legacy Cisco",
        "ip_address": "192.168.0.20",
        "shortname": "legacy1",
        "secret": "netgrid_legacy_secret",
        "nas_type": "cisco",
        "ports": 1812,
        "server": None,
        "community": None,
        "description": "Retired Cisco ASR, kept as an inactive reference",
        "is_active": False,
    },
]

# (username, full_name, email, phone, status, plan name or None, password)
SUBSCRIBERS: list[tuple[str, str, str, str, str, str | None, str]] = [
    (
        "ada.lovelace",
        "Ada Lovelace",
        "ada@example.net",
        "+1-555-0101",
        "active",
        "Fiber",
        "demo-pass-ada",
    ),
    (
        "alan.turing",
        "Alan Turing",
        "alan@example.net",
        "+1-555-0102",
        "active",
        "Fiber",
        "demo-pass-alan",
    ),
    (
        "grace.hopper",
        "Grace Hopper",
        "grace@example.net",
        "+1-555-0103",
        "active",
        "Pro",
        "demo-pass-grace",
    ),
    (
        "katherine.johnson",
        "Katherine Johnson",
        "katherine@example.net",
        "+1-555-0104",
        "active",
        "Pro",
        "demo-pass-katherine",
    ),
    (
        "dorothy.vaughan",
        "Dorothy Vaughan",
        "dorothy@example.net",
        "+1-555-0105",
        "active",
        "Starter",
        "demo-pass-dorothy",
    ),
    (
        "margaret.hamilton",
        "Margaret Hamilton",
        "margaret@example.net",
        "+1-555-0106",
        "active",
        "Starter",
        "demo-pass-margaret",
    ),
    (
        "edith.clarke",
        "Edith Clarke",
        "edith@example.net",
        "+1-555-0107",
        "active",
        "Starter",
        "demo-pass-edith",
    ),
    (
        "frances.allen",
        "Frances Allen",
        "frances@example.net",
        "+1-555-0108",
        "active",
        None,
        "demo-pass-frances",
    ),
    (
        "radia.perlman",
        "Radia Perlman",
        "radia@example.net",
        "+1-555-0109",
        "suspended",
        "Starter",
        "demo-pass-radia",
    ),
    (
        "barbara.liskov",
        "Barbara Liskov",
        "barbara@example.net",
        "+1-555-0110",
        "suspended",
        None,
        "demo-pass-barbara",
    ),
    (
        "shafi.goldwasser",
        "Shafi Goldwasser",
        "shafi@example.net",
        "+1-555-0111",
        "expired",
        "Pro",
        "demo-pass-shafi",
    ),
    (
        "leslie.lamport",
        "Leslie Lamport",
        "leslie@example.net",
        "+1-555-0112",
        "expired",
        None,
        "demo-pass-leslie",
    ),
]

# Invoices per month get paid except for this many (by month index, oldest
# first) so the ledger shows a healthy mix of paid / overdue / issued.
UNPAID_PER_MONTH = {0: 0, 1: 0, 2: 0, 3: 1, 4: 0, 5: 1, 6: 0, 7: 2, 8: 1, 9: 2, 10: 2, 11: 2}
PAYMENT_METHODS = ["card", "bank", "cash"]

# Live sessions: (username, nas ip, session seconds, input octets, output
# octets, framed ip, age).
SESSIONS: list[tuple[str, str, int, int, int, str, timedelta]] = [
    (
        "ada.lovelace",
        "192.168.0.11",
        2 * 3600 + 10 * 60,
        512345678,
        1209876543,
        "10.20.1.11",
        timedelta(hours=2, minutes=10),
    ),
    (
        "alan.turing",
        "192.168.0.11",
        55 * 60,
        241234567,
        310987654,
        "10.20.1.12",
        timedelta(minutes=55),
    ),
    (
        "grace.hopper",
        "192.168.0.10",
        3 * 3600 + 45 * 60,
        892345678,
        2310987654,
        "10.20.0.13",
        timedelta(hours=3, minutes=45),
    ),
    (
        "dorothy.vaughan",
        "192.168.0.10",
        12 * 60,
        45001234,
        98012345,
        "10.20.0.14",
        timedelta(minutes=12),
    ),
    (
        "margaret.hamilton",
        "192.168.0.10",
        26 * 60,
        12345678,
        23456789,
        "10.20.0.15",
        timedelta(minutes=26),
    ),
]


def _last_12_months() -> list[tuple[int, int]]:
    """[(year, month)] for the trailing 12 calendar months, oldest first."""
    months: list[tuple[int, int]] = []
    year, month = date.today().year, date.today().month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


async def _find_actor(session: AsyncSession) -> int:
    """First admin (the seed migration's superadmin in a fresh database)."""
    admin_id = (
        await session.execute(select(Admin.id).order_by(Admin.id).limit(1))
    ).scalar_one_or_none()
    if admin_id is None:
        raise RuntimeError(
            "No admin found — run `alembic upgrade head` first "
            "(the seed migration creates the superadmin account)."
        )
    return int(admin_id)


# ---------------------------------------------------------------------------
# Core seeding — one section per call, each idempotent
# ---------------------------------------------------------------------------


async def seed_plans(session: AsyncSession, *, actor_id: int) -> int:
    """Create the plan set + radgroupreply rows; 0 when plans already exist."""
    count = (await session.execute(select(func.count()).select_from(Plan))).scalar_one()
    if count:
        return 0
    for plan in PLANS:
        await plans_service.create_plan(session, actor_id=actor_id, **plan)
    return len(PLANS)


async def seed_nas_devices(session: AsyncSession, *, actor_id: int) -> int:
    """Create NAS devices + their FreeRADIUS nas rows; 0 when any exist."""
    count = (
        await session.execute(select(func.count()).select_from(nas_service.NasDevice))
    ).scalar_one()
    if count:
        return 0
    for device in NAS_DEVICES:
        await nas_service.create_nas_device(session, actor_id=actor_id, **device)
    return len(NAS_DEVICES)


async def seed_subscribers(session: AsyncSession, *, actor_id: int) -> int:
    """Create subscribers + radcheck/radusergroup rows; 0 when any exist."""
    count = (
        await session.execute(select(func.count()).select_from(subs_service.Subscriber))
    ).scalar_one()
    if count:
        return 0
    # plan name -> id, so a fresh seed can assign plans by name; unknown
    # names (a pre-existing database with different plans) fall back to no plan.
    plan_rows = (await session.execute(select(Plan.name, Plan.id))).all()
    plan_ids = {name: plan_id for name, plan_id in plan_rows}
    for username, full_name, email, phone, status, plan_name, password in SUBSCRIBERS:
        await subs_service.create_subscriber(
            session,
            actor_id=actor_id,
            username=username,
            full_name=full_name,
            email=email,
            phone=phone,
            status=status,
            password=password,
            plan_id=plan_ids.get(plan_name) if plan_name else None,
        )
    return len(SUBSCRIBERS)


async def seed_invoices(session: AsyncSession, *, actor_id: int) -> int:
    """Bill active subscribers for the trailing 12 months; 0 when any exist."""
    count = (
        await session.execute(select(func.count()).select_from(billing_service.Invoice))
    ).scalar_one()
    if count:
        return 0
    created = 0
    for year, month in _last_12_months():
        _, last = calendar.monthrange(year, month)
        created += await billing_service.generate_invoices(
            session,
            period_start=date(year, month, 1),
            period_end=date(year, month, last),
            actor_id=actor_id,
        )
    return created


async def seed_payments(session: AsyncSession, *, actor_id: int) -> int:
    """Pay a deterministic subset of each month's invoices, backdated.

    Payment timestamps are moved to the 15th of the invoice's billing month
    so the revenue report (grouped by payment month) shows 12 populated
    buckets instead of a single spike. 0 when any payments already exist.
    """
    count = (await session.execute(select(func.count()).select_from(Payment))).scalar_one()
    if count:
        return 0
    invoices, _ = await billing_service.list_invoices(session, page=1, page_size=1000)
    by_month: dict[tuple[int, int], list] = {}
    for invoice in invoices:
        key = (invoice.period_start.year, invoice.period_start.month)
        by_month.setdefault(key, []).append(invoice)
    for month_idx, ((year, month), month_invoices) in enumerate(sorted(by_month.items())):
        unpaid = UNPAID_PER_MONTH.get(month_idx, 0)
        payable = month_invoices[:-unpaid] if unpaid else month_invoices
        for position, invoice in enumerate(payable):
            reference = f"seed-{year}-{month:02d}-{position}"
            payment = await billing_service.record_payment(
                session,
                invoice,
                actor_id=actor_id,
                amount=invoice.amount,
                method=PAYMENT_METHODS[(month_idx + position) % len(PAYMENT_METHODS)],
                reference=reference,
            )
            # Backdate to the 15th of the billing month.
            payment.created_at = datetime(year, month, 15, 10, 0, 0)
    await session.commit()
    return int((await session.execute(select(func.count()).select_from(Payment))).scalar_one())


async def seed_overdue(session: AsyncSession) -> int:
    """Flip issued invoices whose due date has passed to overdue."""
    return await billing_service.mark_overdue_invoices(session)


async def seed_sessions(session: AsyncSession) -> int:
    """Insert open radacct rows for the live-sessions cards; 0 when any exist."""
    open_count = (
        await session.execute(
            select(func.count()).select_from(RadAcct).where(RadAcct.acctstoptime.is_(None))
        )
    ).scalar_one()
    if open_count:
        return 0
    now = datetime.now(UTC)
    for index, (username, nas_ip, seconds, down, up, framed_ip, age) in enumerate(SESSIONS):
        session.add(
            RadAcct(
                acctsessionid=f"seed-sess-{index}",
                acctuniqueid=f"seed-uniq-{index}",
                username=username,
                nasipaddress=nas_ip,
                acctstarttime=now - age,
                acctsessiontime=seconds,
                acctinputoctets=down,
                acctoutputoctets=up,
                framedipaddress=framed_ip,
            )
        )
    await session.commit()
    return len(SESSIONS)


async def seed_dev(session: AsyncSession, *, actor_id: int | None = None) -> dict[str, int]:
    """Run every section; returns {section: rows created} (0 = skipped)."""
    if actor_id is None:
        actor_id = await _find_actor(session)
    return {
        "plans": await seed_plans(session, actor_id=actor_id),
        "nas_devices": await seed_nas_devices(session, actor_id=actor_id),
        "subscribers": await seed_subscribers(session, actor_id=actor_id),
        "invoices": await seed_invoices(session, actor_id=actor_id),
        "payments": await seed_payments(session, actor_id=actor_id),
        "overdue_flips": await seed_overdue(session),
        "live_sessions": await seed_sessions(session),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _check_radius_schema(session: AsyncSession) -> None:
    """Fail with a clear message when the FreeRADIUS rad* tables are absent.

    Alembic migrations only create the app's own tables; the rad* tables
    come from the FreeRADIUS schema.sql (applied by the compose postgres at
    init). Without them the seed would die on a raw ProgrammingError deep
    inside a service call.
    """
    try:
        await session.execute(text("SELECT 1 FROM radcheck LIMIT 1"))
    except ProgrammingError as exc:
        if "does not exist" in str(exc):
            raise RuntimeError(
                "The FreeRADIUS schema tables are missing (no radcheck). Apply "
                "freeradius/raddb/mods-config/sql/main/postgresql/schema.sql "
                "(the compose postgres does this automatically on a fresh volume) "
                "and re-run."
            ) from exc
        raise


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await _check_radius_schema(session)
            actor_id = await _find_actor(session)
            print(f"seeding against {settings.database_url} (actor admin #{actor_id})")
            counts = await seed_dev(session, actor_id=actor_id)
    finally:
        await engine.dispose()
    print("done:")
    for section, created in counts.items():
        state = f"{created} created" if created else "0 — already present or nothing to do"
        print(f"  {section:<16} {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
