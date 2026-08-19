"""Pydantic schemas for subscriber resources (Phase 5)."""

from pydantic import BaseModel


class SubscriberStats(BaseModel):
    """Status-count snapshot for the dashboard.

    Counts the three known statuses (active | suspended | expired); total is
    the count of all subscriber rows, so it stays correct even if an unknown
    status value appears in the data.
    """

    active: int
    suspended: int
    expired: int
    total: int
