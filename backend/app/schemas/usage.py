"""Pydantic schemas for the data-cap usage report (usage:read)."""

from datetime import datetime

from pydantic import BaseModel


class UsageReportItem(BaseModel):
    """One plan-assigned subscriber's current-month consumption vs quota."""

    subscriber_id: int
    username: str
    full_name: str
    plan_id: int
    plan_name: str
    quota_gb: int | None
    enforce_quota: bool
    window_start: datetime
    window_end: datetime
    input_octets: int
    output_octets: int
    total_octets: int
    total_gb: float
    session_count: int
    pct_used: float | None


class UsageStats(BaseModel):
    """Rollup for the dashboard card header."""

    total_consumed_gb: float
    over_quota_count: int


class UsageReport(BaseModel):
    """Per-subscriber usage vs quota plus a rollup."""

    items: list[UsageReportItem]
    total: int
    stats: UsageStats


class SubscriberUsageMonth(BaseModel):
    """One calendar month of consumption for a single subscriber's profile."""

    month: str  # "YYYY-MM"
    start: datetime
    end: datetime
    input_octets: int
    output_octets: int
    total_octets: int
    total_gb: float
    session_count: int
    quota_gb: int | None
    pct_used: float | None
