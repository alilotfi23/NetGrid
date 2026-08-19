"""Pydantic schemas for subscriber management (Phase 5)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^\S+$"
SubscriberStatus = Literal["active", "suspended", "expired"]


class PlanSubscriberCount(BaseModel):
    """Per-plan subscriber total (all statuses), for the dashboard breakdown."""

    plan_id: int | None
    plan_name: str | None
    count: int


class PlanStatusCount(BaseModel):
    """One cell of the status-by-plan matrix: subscribers of one status on one plan."""

    plan_id: int | None
    plan_name: str | None
    status: str
    count: int


class SubscriberStats(BaseModel):
    """Status-count snapshot for the dashboard.

    Counts the three known statuses (active | suspended | expired); total is
    the count of all subscriber rows, so it stays correct even if an unknown
    status value appears in the data. `by_plan` breaks the total down per
    plan (all statuses); `by_plan_status` is the status-by-plan matrix (one
    row per non-empty plan+status cell). Subscribers without a plan have
    plan_id None.
    """

    active: int
    suspended: int
    expired: int
    total: int
    by_plan: list[PlanSubscriberCount] = Field(default_factory=list)
    by_plan_status: list[PlanStatusCount] = Field(default_factory=list)


class SubscriberHistoryEntry(BaseModel):
    """One audit event on a subscriber, for the profile's history timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    metadata_: dict[str, object] | None = None
    created_at: datetime


class LiveSessionOut(BaseModel):
    """A live (open) radacct session, for the profile view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None = None
    nasipaddress: str | None = None
    nas_shortname: str | None = None  # from the nas table; null when unknown
    subscriber_id: int | None = None  # profile id; null when no subscriber row
    acctstarttime: datetime | None = None
    acctsessiontime: int | None = None
    acctinputoctets: int | None = None
    acctoutputoctets: int | None = None
    framedipaddress: str | None = None


class SubscriberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    status: str
    plan_id: int | None = None  # NULL until Phase 6 writes radusergroup
    notes: str | None = None
    created_at: datetime


class SubscriberCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    status: SubscriberStatus = "active"
    plan_id: int | None = None  # Phase 6: writes radusergroup on assignment
    notes: str | None = Field(default=None, max_length=2000)


class SubscriberUpdate(BaseModel):
    # username is intentionally absent — immutable after creation
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    status: SubscriberStatus | None = None
    plan_id: int | None = None  # Phase 6: set to switch plans, null to clear
    notes: str | None = Field(default=None, max_length=2000)
