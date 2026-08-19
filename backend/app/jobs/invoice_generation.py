"""Monthly invoice generation job (Phase 10).

Runs on the first day of each month at 00:05: bills every active subscriber
on an active plan for the current calendar month and flips any invoices whose
due date has passed to ``overdue``. Idempotent — re-running (or a manual
``POST /invoices/generate``) never double-bills a subscriber for an
overlapping period.
"""

import logging
from collections.abc import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.services import billing as billing_service

logger = logging.getLogger(__name__)

JOB_ID = "monthly-invoice-generation"


async def run_invoice_generation(session: AsyncSession) -> int:
    """One generation pass: create invoices + mark overdue. Returns created count."""
    created = await billing_service.generate_invoices(session)
    overdue = await billing_service.mark_overdue_invoices(session)
    logger.info("invoice generation: created=%s overdue=%s", created, overdue)
    return created


async def _job_body() -> None:
    async for session in _sessions():
        await run_invoice_generation(session)


async def _sessions() -> AsyncIterator[AsyncSession]:
    """Yield one DB session for the job (get_session is an async generator)."""
    async for session in get_session():
        yield session


def build_scheduler() -> AsyncIOScheduler:
    """The app-wide scheduler with the invoice job registered (CronTrigger)."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _job_body,
        CronTrigger(day=1, hour=0, minute=5),
        id=JOB_ID,
        replace_existing=True,
    )
    return scheduler
