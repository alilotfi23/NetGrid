"""Pydantic schemas for plans / RADIUS groups (Phase 6)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

NAME_PATTERN = r"^\S+$"


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    radius_group: str
    price: Decimal
    duration_days: int
    bandwidth_down_mbps: int
    bandwidth_up_mbps: int
    quota_gb: int | None = None
    description: str | None = None
    is_active: bool
    enforce_quota: bool
    overage_price_per_gb: Decimal | None = None
    created_at: datetime
    # populated by the API from a grouped subscriber count (not a Plan column)
    subscriber_count: int = 0


class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=NAME_PATTERN)
    radius_group: str = Field(min_length=1, max_length=64, pattern=NAME_PATTERN)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    duration_days: int = Field(ge=1, le=3650)
    bandwidth_down_mbps: int = Field(ge=0, le=100_000)
    bandwidth_up_mbps: int = Field(ge=0, le=100_000)
    quota_gb: int | None = Field(default=None, ge=0, le=1_000_000)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    enforce_quota: bool = False
    overage_price_per_gb: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )


class PlanUpdate(BaseModel):
    # name and radius_group are intentionally absent — they are the plan's
    # RADIUS identity and immutable after creation (rename = recreate)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    bandwidth_down_mbps: int | None = Field(default=None, ge=0, le=100_000)
    bandwidth_up_mbps: int | None = Field(default=None, ge=0, le=100_000)
    quota_gb: int | None = Field(default=None, ge=0, le=1_000_000)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    enforce_quota: bool | None = None
    overage_price_per_gb: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
