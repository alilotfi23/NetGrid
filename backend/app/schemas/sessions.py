"""Pydantic schemas for live sessions (Phase 9)."""

from typing import Literal

from pydantic import BaseModel

from app.core.pagination import Page
from app.schemas.subscribers import LiveSessionOut


class DisconnectResult(BaseModel):
    """Outcome of a Disconnect-Request sent to the session's NAS.

    Only a Disconnect-ACK returns here — NAK/timeout surface as errors
    (409 CONFLICT / 502 BAD_GATEWAY).
    """

    status: Literal["disconnected"]


class SessionNasCount(BaseModel):
    """Open sessions grouped by the NAS they run on.

    nas_shortname is the device's shortname from the nas table (joined on
    nasname), or None when the NAS IP has no row there.
    """

    nasipaddress: str
    count: int
    nas_shortname: str | None = None


class SessionStats(BaseModel):
    """Global live-session counts for the dashboard card.

    by_nas is sorted by count descending so the busiest NAS leads.
    """

    total: int
    by_nas: list[SessionNasCount]


class SessionList(Page[LiveSessionOut]):
    """The list response — the paginated page plus global stats."""

    stats: SessionStats
