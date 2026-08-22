"""Invoice and payment endpoints (Phase 10).

Permissions:
  invoices:read   — list invoices, get invoice detail
  invoices:write  — manual invoice generation, record payments
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.billing import (
    InvoiceGenerateRequest,
    InvoiceGenerateResult,
    InvoiceList,
    InvoiceOut,
    InvoiceStats,
    PaymentCreate,
    PaymentOut,
    PaymentReport,
    PaymentResult,
)
from app.services import billing as billing_service

router = APIRouter(prefix="/invoices", tags=["invoices"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=InvoiceList)
@limiter.limit(LIMITS["invoice_read"])
async def list_invoices(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("invoices:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subscriber_id: int | None = Query(None, ge=1),
    status: str | None = Query(None, pattern="^(issued|paid|overdue)$"),
) -> InvoiceList:
    """GET /api/v1/invoices — requires invoices:read.

    Paginated invoice list with global `stats` (status counts + outstanding
    amount). `subscriber_id` filters to one subscriber, `status` to a single
    invoice status (issued | paid | overdue).
    """
    items, total = await billing_service.list_invoices(
        session, page, page_size, subscriber_id=subscriber_id, status=status
    )
    stats = await billing_service.get_invoice_stats(session)
    usernames = await billing_service.get_subscriber_usernames(
        session, [inv.subscriber_id for inv in items]
    )
    items_out = []
    for inv in items:
        out = InvoiceOut.model_validate(inv)
        out.subscriber_username = usernames.get(inv.subscriber_id)
        items_out.append(out)
    return InvoiceList(
        items=items_out,
        total=total,
        page=page,
        page_size=page_size,
        stats=InvoiceStats(**stats),
    )


# Route order matters: these static paths must stay ahead of `/{invoice_id}`
# so "generate"/"report" are never parsed as int ids.
@router.get("/report", response_model=PaymentReport)
@limiter.limit(LIMITS["invoice_read"])
async def payments_report(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("invoices:read"))],
    year: int | None = Query(None, ge=2000, le=2100),
) -> PaymentReport:
    """GET /api/v1/invoices/report — requires invoices:read.

    Revenue grouped by (month, method) for completed payments, newest month
    first, with the grand total. `year` narrows to one calendar year.
    """
    return PaymentReport(**await billing_service.get_payments_report(session, year=year))


@router.post("/generate", response_model=InvoiceGenerateResult)
@limiter.limit(LIMITS["invoice_write"])
async def generate_invoices(
    request: Request,
    response: Response,
    payload: InvoiceGenerateRequest,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("invoices:write"))],
) -> InvoiceGenerateResult:
    """POST /api/v1/invoices/generate — requires invoices:write.

    Manual trigger of the monthly invoice job for the current calendar month
    (or an explicit period). Idempotent — subscribers already invoiced for an
    overlapping period are skipped.
    """
    created = await billing_service.generate_invoices(
        session,
        period_start=payload.period_start,
        period_end=payload.period_end,
        actor_id=actor.id,
    )
    return InvoiceGenerateResult(created=created)


@router.post("/overage/generate", response_model=InvoiceGenerateResult)
@limiter.limit(LIMITS["invoice_write"])
async def generate_overage_invoices(
    request: Request,
    response: Response,
    payload: InvoiceGenerateRequest,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("invoices:write"))],
) -> InvoiceGenerateResult:
    """POST /api/v1/invoices/overage/generate — requires invoices:write.

    Manual trigger of the usage overage sweep: bills per-GB surcharges for
    consumption beyond plan quota in a completed period (defaults to the
    previous calendar month). Idempotent — a subscriber already surcharged
    for the period is skipped.
    """
    created = await billing_service.generate_overage_invoices(
        session,
        period_start=payload.period_start,
        period_end=payload.period_end,
        actor_id=actor.id,
    )
    return InvoiceGenerateResult(created=created)


@router.get("/{invoice_id}", response_model=InvoiceOut)
@limiter.limit(LIMITS["invoice_read"])
async def get_invoice(
    request: Request,
    response: Response,
    invoice_id: int,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("invoices:read"))],
) -> InvoiceOut:
    """GET /api/v1/invoices/{id} — requires invoices:read.

    Invoice detail including its payments.
    """
    invoice = await billing_service.get_invoice_or_404(session, invoice_id)
    out = InvoiceOut.model_validate(invoice)
    usernames = await billing_service.get_subscriber_usernames(session, [invoice.subscriber_id])
    out.subscriber_username = usernames.get(invoice.subscriber_id)
    return out


@router.post("/{invoice_id}/payments", response_model=PaymentResult, status_code=201)
@limiter.limit(LIMITS["invoice_write"])
async def record_payment(
    request: Request,
    response: Response,
    invoice_id: int,
    payload: PaymentCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("invoices:write"))],
) -> PaymentResult:
    """POST /api/v1/invoices/{id}/payments — requires invoices:write.

    Records a completed payment; the invoice flips to paid when completed
    payments reach its amount. Partial payments are allowed.
    """
    invoice = await billing_service.get_invoice_or_404(session, invoice_id)
    payment = await billing_service.record_payment(
        session,
        invoice,
        actor_id=actor.id,
        amount=payload.amount,
        method=payload.method,
        reference=payload.reference,
    )
    invoice = await billing_service.get_invoice_or_404(session, invoice_id)
    usernames = await billing_service.get_subscriber_usernames(session, [invoice.subscriber_id])
    invoice_out = InvoiceOut.model_validate(invoice)
    invoice_out.subscriber_username = usernames.get(invoice.subscriber_id)
    return PaymentResult(payment=PaymentOut.model_validate(payment), invoice=invoice_out)
