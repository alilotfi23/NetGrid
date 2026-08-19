"""Pydantic schemas for billing: invoices and payments (Phase 10)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page

# Invoice statuses — keep in sync with app/services/billing.py
INVOICE_STATUSES = ("issued", "paid", "overdue")
PAYMENT_METHODS = ("cash", "card", "bank_transfer", "wallet", "other")


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount: Decimal
    method: str
    reference: str | None = None
    status: str
    created_at: datetime


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscriber_id: int
    subscriber_username: str | None = None  # joined by the API layer, not a column
    plan_name: str
    period_start: date
    period_end: date
    amount: Decimal
    status: str
    issued_at: datetime
    due_at: date
    paid_at: datetime | None = None
    payments: list[PaymentOut] = Field(default_factory=list)


class InvoiceStats(BaseModel):
    """Status-count snapshot plus the outstanding (unpaid) total."""

    issued: int
    paid: int
    overdue: int
    outstanding_amount: Decimal


class InvoiceList(Page[InvoiceOut]):
    """The list response — the paginated page plus global stats."""

    stats: InvoiceStats


class InvoiceGenerateRequest(BaseModel):
    """Optional period override for the manual generate action.

    Omitted fields default to the current calendar month.
    """

    period_start: date | None = None
    period_end: date | None = None


class InvoiceGenerateResult(BaseModel):
    created: int


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: str = Field(min_length=1, max_length=32)
    reference: str | None = Field(default=None, max_length=128)


class PaymentResult(BaseModel):
    """The payment plus the invoice it was recorded against (post-transition)."""

    payment: PaymentOut
    invoice: InvoiceOut


class PaymentReportRow(BaseModel):
    """One (month, method) bucket of the revenue report."""

    month: str  # YYYY-MM
    method: str
    revenue: Decimal
    count: int


class PaymentReport(BaseModel):
    """Revenue grouped by month and payment method (completed payments only)."""

    items: list[PaymentReportRow]
    total_revenue: Decimal
