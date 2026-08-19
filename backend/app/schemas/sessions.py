"""Pydantic schemas for live sessions (Phase 9, read side)."""

from pydantic import BaseModel

from app.core.pagination import Page
from app.schemas.subscribers import LiveSessionOut


class SessionNasCount(BaseModel):
    """Open sessions grouped by the NAS they run on."""

    nasipaddress: str
    count: int


class SessionStats(BaseModel):
    """Global live-session counts for the dashboard card.

    by_nas is sorted by count descending so the busiest NAS leads.
    """

    total: int
    by_nas: list[SessionNasCount]


class SessionList(Page[LiveSessionOut]):
    """The list response — the paginated page plus global stats."""

    stats: SessionStats
