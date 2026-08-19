"""Pydantic schemas for subscriber management (Phase 5)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^\S+$"
SubscriberStatus = Literal["active", "suspended", "expired"]


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
    notes: str | None = Field(default=None, max_length=2000)


class SubscriberUpdate(BaseModel):
    # username is intentionally absent — immutable after creation
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    status: SubscriberStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
