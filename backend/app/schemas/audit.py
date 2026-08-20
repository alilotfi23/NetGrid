"""Pydantic schemas for the audit log (Phase 12 viewer)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.pagination import Page


class AuditLogOut(BaseModel):
    """One audit entry. ``admin_username`` is joined by the API layer, not a column."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int | None = None
    admin_username: str | None = None
    action: str
    resource: str
    resource_id: str | None = None
    metadata_: dict[str, object] | None = None
    created_at: datetime


class AuditActorOption(BaseModel):
    """An admin who appears as an actor in the log, for the actor filter."""

    id: int
    username: str


class AuditLogFilters(BaseModel):
    """Distinct filter values present in the log, for the dashboard dropdowns."""

    actions: list[str]
    resources: list[str]
    admins: list[AuditActorOption]


class AuditLogList(Page[AuditLogOut]):
    """The list response — the paginated page plus the filter options."""

    filters: AuditLogFilters
