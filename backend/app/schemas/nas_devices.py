"""Pydantic schemas for NAS devices (Phase 7)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page

NAME_PATTERN = r"^\S+$"


class NasDeviceTypeCount(BaseModel):
    """Devices grouped by nas_type for the by-type breakdown card."""

    nas_type: str
    count: int


class NasDeviceStats(BaseModel):
    """Global NAS device counts for the dashboard summary card."""

    total: int
    active: int
    inactive: int
    by_type: list[NasDeviceTypeCount]


class NasDeviceOut(BaseModel):
    """NAS device as seen by the dashboard.

    The shared secret is never returned — it lives Fernet-encrypted in
    nas_devices.secret_encrypted and plaintext in the FreeRADIUS nas table.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    ip_address: str
    shortname: str
    nas_type: str
    ports: int | None = None
    server: str | None = None
    community: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime


class NasDeviceList(Page[NasDeviceOut]):
    """The list response — the paginated page plus global counts.

    Stats are global (all devices), not scoped to the page, so the dashboard
    card stays correct regardless of pagination.
    """

    stats: NasDeviceStats


class NasDeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=NAME_PATTERN)
    ip_address: str = Field(min_length=1, max_length=45, pattern=NAME_PATTERN)
    shortname: str = Field(min_length=1, max_length=64, pattern=NAME_PATTERN)
    nas_type: str = Field(default="other", min_length=1, max_length=32, pattern=NAME_PATTERN)
    # RADIUS shared secrets are at most 63 characters (RFC 2865 attribute space)
    secret: str = Field(min_length=1, max_length=63)
    ports: int | None = Field(default=None, ge=1, le=65535)
    server: str | None = Field(default=None, max_length=64)
    community: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class NasDeviceUpdate(BaseModel):
    # ip_address is intentionally absent — it is the device's RADIUS identity
    # (nas.nasname) and immutable after creation (rename = recreate)
    name: str | None = Field(default=None, min_length=1, max_length=64, pattern=NAME_PATTERN)
    shortname: str | None = Field(default=None, min_length=1, max_length=64, pattern=NAME_PATTERN)
    nas_type: str | None = Field(default=None, min_length=1, max_length=32, pattern=NAME_PATTERN)
    secret: str | None = Field(default=None, min_length=1, max_length=63)
    ports: int | None = Field(default=None, ge=1, le=65535)
    server: str | None = Field(default=None, max_length=64)
    community: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class NasDeviceSecretRotate(BaseModel):
    """Payload for the dedicated secret-rotation action.

    Rotation re-encrypts the at-rest copy and rewrites the plaintext secret on
    the FreeRADIUS nas row (active devices) without touching any other field.
    """

    secret: str = Field(min_length=1, max_length=63)
