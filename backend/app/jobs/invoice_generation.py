"""Scheduled background jobs: billing (Phase 10) + over-quota enforcement.

The app-wide scheduler is assembled here (main.py imports build_scheduler);
three independent jobs, each with its own schedule:

1. ``monthly-invoice-generation`` — first day of each month at 00:05 UTC:
   bills every active subscriber on an active plan for the current calendar
   month. Idempotent — re-running (or a manual ``POST /invoices/generate``)
   never double-bills a subscriber for an overlapping period.

2. ``daily-overdue-sweep`` — every day at 00:10 UTC: flips invoices whose
   due date has passed from ``issued`` to ``overdue``. This runs daily (not
   monthly) so a subscriber's status reflects reality as soon as a due date
   passes, instead of waiting for the next month's generation job.

3. ``quota-enforcement`` — every N minutes (configurable): disconnects live
   sessions of subscribers at/over quota on enforcement-enabled plans, via
   the same pyrad CoA path as the sessions API (see app.jobs.quota_enforcement).

4. ``overage-billing`` — on the 2nd of each month at 00:15 UTC: bills
   per-GB surcharges for consumption beyond plan quota in the *previous*
   (now closed) month, from the radacct usage report (see
   generate_overage_invoices in app.services.billing). It runs a day after
   the monthly generation so the base invoices exist first, and after the
   daily overdue sweep so fresh surcharges start ``issued``.
"""

import logging
from collections.abc import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.jobs.quota_enforcement import JOB_ID_QUOTA_ENFORCEMENT, _quota_enforcement_body
from app.services import billing as billing_service

logger = logging.getLogger(__name__)

JOB_ID_MONTHLY_GENERATION = "monthly-invoice-generation"
JOB_ID_DAILY_OVERDUE_SWEEP = "daily-overdue-sweep"
JOB_ID_OVERAGE_BILLING = "overage-billing"

# Staggered so the monthly job (00:05) finishes before the daily sweep (00:10)
# runs — a fresh invoice is never past-due, but the order keeps both cheap.
MONTHLY_GENERATION_CRON = CronTrigger(day=1, hour=0, minute=5)
DAILY_OVERDUE_SWEEP_CRON = CronTrigger(hour=0, minute=10)
OVERAGE_BILLING_CRON = CronTrigger(day=2, hour=0, minute=15)


async def run_invoice_generation(session: AsyncSession) -> int:
    """Generate this month's invoices. Returns the number created."""
    created = await billing_service.generate_invoices(session)
    logger.info("invoice generation: created=%s", created)
    return created


async def run_overdue_sweep(session: AsyncSession) -> int:
    """Flip issued invoices past their due date to overdue. Returns count."""
    overdue = await billing_service.mark_overdue_invoices(session)
    logger.info("overdue sweep: marked=%s", overdue)
    return overdue


async def _monthly_generation_body() -> None:
    async for session in _sessions():
        await run_invoice_generation(session)


async def _daily_sweep_body() -> None:
    async for session in _sessions():
        await run_overdue_sweep(session)


async def run_overage_billing(session: AsyncSession) -> int:
    """Bill previous-month usage surcharges. Returns the number created."""
    created = await billing_service.generate_overage_invoices(session)
    logger.info("overage billing: created=%s", created)
    return created


async def _overage_billing_body() -> None:
    async for session in _sessions():
        await run_overage_billing(session)


async def _sessions() -> AsyncIterator[AsyncSession]:
    """Yield one DB session for the job (get_session is an async generator)."""
    async for session in get_session():
        yield session


def build_scheduler() -> AsyncIOScheduler:
    """The app-wide scheduler with the billing + quota-enforcement jobs."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _monthly_generation_body,
        MONTHLY_GENERATION_CRON,
        id=JOB_ID_MONTHLY_GENERATION,
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_sweep_body,
        DAILY_OVERDUE_SWEEP_CRON,
        id=JOB_ID_DAILY_OVERDUE_SWEEP,
        replace_existing=True,
    )
    scheduler.add_job(
        _quota_enforcement_body,
        IntervalTrigger(minutes=get_settings().quota_enforcement_interval_minutes),
        id=JOB_ID_QUOTA_ENFORCEMENT,
        replace_existing=True,
    )
    scheduler.add_job(
        _overage_billing_body,
        OVERAGE_BILLING_CRON,
        id=JOB_ID_OVERAGE_BILLING,
        replace_existing=True,
    )
    return scheduler
