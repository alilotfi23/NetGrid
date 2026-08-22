"""Usage-aggregation service: current-period per-subscriber octet totals.

Read-only against FreeRADIUS's ``radacct`` table — the app never writes it
(FreeRADIUS owns accounting). The default window is the current UTC calendar
month, and a session's octets are attributed to the month in which it
*started* (``acctstarttime``), closed or not: open sessions carry whatever the
NAS last reported via interim-updates, which is exactly what a live usage
view needs.

The per-subscriber read (``get_subscriber_usage``) is wrapped in a best-effort
short-TTL Redis cache mirroring the RBAC permission cache: a Redis outage
falls back to a direct query, and the 60s TTL keeps the dashboard/API from
serving stale consumptions for longer than a short window. The bulk
``summarize_usage`` is deliberately uncached so enforcement/report jobs always
read near-fresh numbers.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.plan import Plan
from app.models.radius import RadAcct
from app.models.subscriber import Subscriber

# Mirrors PERM_CACHE_TTL_SECONDS: quota numbers are never stale for longer
# than a short window, and the dashboard's live-polling cards refresh within it.
CACHE_TTL_SECONDS = 60

# Under pytest-xdist each worker runs its own database with the same demo
# usernames, so a cache keyed only by username+window would serve one
# worker's consumption to another. Namespace by worker when running in
# parallel (same pattern as the RBAC permission cache).
_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
_CACHE_PREFIX = f"usage:{_worker}:" if _worker else "usage:"


@dataclass(frozen=True)
class SubscriberUsage:
    """Octet consumption for one username over one window."""

    username: str
    start: datetime
    end: datetime
    input_octets: int
    output_octets: int
    session_count: int

    @property
    def total_octets(self) -> int:
        return self.input_octets + self.output_octets

    def to_dict(self) -> dict[str, object]:
        return {
            "username": self.username,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "input_octets": self.input_octets,
            "output_octets": self.output_octets,
            "total_octets": self.total_octets,
            "session_count": self.session_count,
        }


def month_window(reference: datetime | None = None) -> tuple[datetime, datetime]:
    """[first instant of the month, first instant of the next month) in UTC."""
    ref = (reference or datetime.now(UTC)).astimezone(UTC)
    start = datetime(ref.year, ref.month, 1, tzinfo=UTC)
    if ref.month == 12:
        end = datetime(ref.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(ref.year, ref.month + 1, 1, tzinfo=UTC)
    return start, end


async def summarize_usage(
    session: AsyncSession,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    usernames: list[str] | None = None,
) -> list[SubscriberUsage]:
    """Octet totals per username over [start, end); defaults to the current month.

    Only usernames with at least one counted session appear — a subscriber
    with no traffic has no row here (the caller joins the subscriber list to
    render zeros). Octets are attributed by the *start* of each session, so a
    session that began last month and closed this month is billed to last
    month; rows with NULL octet counters coalesce to 0 but still count as a
    session.
    """
    if start is None or end is None:
        start, end = month_window()
    stmt = (
        select(
            RadAcct.username,
            func.coalesce(func.sum(RadAcct.acctinputoctets), 0).label("input_octets"),
            func.coalesce(func.sum(RadAcct.acctoutputoctets), 0).label("output_octets"),
            func.count().label("session_count"),
        )
        .where(RadAcct.acctstarttime >= start, RadAcct.acctstarttime < end)
        .group_by(RadAcct.username)
        .order_by(RadAcct.username)
    )
    if usernames:
        stmt = stmt.where(RadAcct.username.in_(usernames))
    rows = (await session.execute(stmt)).all()
    return [
        SubscriberUsage(
            username=username,
            start=start,
            end=end,
            input_octets=int(input_octets or 0),
            output_octets=int(output_octets or 0),
            session_count=int(session_count),
        )
        for username, input_octets, output_octets, session_count in rows
    ]


def _cache_key(username: str, start: datetime, end: datetime) -> str:
    stamp = f"{start.isoformat()}/{end.isoformat()}"
    return f"{_CACHE_PREFIX}sub:{stamp}:{username}"


async def _read_cache(key: str) -> SubscriberUsage | None:
    try:
        redis = get_redis()
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            return SubscriberUsage(
                username=data["username"],
                start=datetime.fromisoformat(data["start"]),
                end=datetime.fromisoformat(data["end"]),
                input_octets=data["input_octets"],
                output_octets=data["output_octets"],
                session_count=data["session_count"],
            )
        finally:
            await redis.aclose()
    except Exception:
        return None  # cache outage -> direct query


async def _write_cache(key: str, usage: SubscriberUsage) -> None:
    try:
        redis = get_redis()
        try:
            await redis.set(key, json.dumps(usage.to_dict()), ex=CACHE_TTL_SECONDS)
        finally:
            await redis.aclose()
    except Exception:
        pass  # best-effort; TTL self-heals


async def get_subscriber_usage(
    session: AsyncSession,
    username: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> SubscriberUsage:
    """Cached usage for one username over the window (default current month).

    Returns a zeroed record when the username has no session rows in the
    window, so callers never special-case "no traffic yet". The cache is keyed
    by username+window and cached for CACHE_TTL_SECONDS; clear_usage_cache()
    invalidates it (used by the permission-style invalidation path and tests).
    """
    if start is None or end is None:
        start, end = month_window()
    key = _cache_key(username, start, end)
    cached = await _read_cache(key)
    if cached is not None:
        return cached
    rows = await summarize_usage(session, start=start, end=end, usernames=[username])
    usage = (
        rows[0]
        if rows
        else SubscriberUsage(
            username=username,
            start=start,
            end=end,
            input_octets=0,
            output_octets=0,
            session_count=0,
        )
    )
    await _write_cache(key, usage)
    return usage


async def clear_usage_cache() -> None:
    """Drop every cached usage record (call after reprovisioning, in tests)."""
    redis = get_redis()
    try:
        async for key in redis.scan_iter(f"{_CACHE_PREFIX}*"):
            await redis.delete(key)
    except Exception:
        pass  # keys expire on their own
    finally:
        await redis.aclose()


# ---------------------------------------------------------------------------
# Data-cap report (usage vs plan quota)
# ---------------------------------------------------------------------------

_GB = 1024**3


def octets_to_gb(octets: int) -> float:
    """GiB, rounded to two decimals (1 GiB = 1024^3 bytes)."""
    return round(octets / _GB, 2)


@dataclass(frozen=True)
class UsageReportRow:
    """One plan-assigned subscriber's consumption vs its plan quota."""

    subscriber_id: int
    username: str
    full_name: str
    plan_id: int
    plan_name: str
    quota_gb: int | None
    window_start: datetime
    window_end: datetime
    input_octets: int
    output_octets: int
    session_count: int

    @property
    def total_octets(self) -> int:
        return self.input_octets + self.output_octets

    @property
    def total_gb(self) -> float:
        return octets_to_gb(self.total_octets)

    @property
    def pct_used(self) -> float | None:
        """Percent of the plan quota consumed; None when the plan has no cap."""
        if not self.quota_gb:
            return None
        return round(self.total_gb / self.quota_gb * 100, 1)

    def to_dict(self) -> dict[str, object]:
        return {
            "subscriber_id": self.subscriber_id,
            "username": self.username,
            "full_name": self.full_name,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "quota_gb": self.quota_gb,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "input_octets": self.input_octets,
            "output_octets": self.output_octets,
            "total_octets": self.total_octets,
            "total_gb": self.total_gb,
            "session_count": self.session_count,
            "pct_used": self.pct_used,
        }


async def get_usage_report(session: AsyncSession) -> list[UsageReportRow]:
    """Current-month consumption vs plan quota for every plan-assigned subscriber.

    Subscribers without any session rows in the window appear with zero usage
    (their quota still shows), so the operator sees the whole book, not just
    who has traffic. Ordered by username. Unplanned subscribers are excluded
    — they have no cap to track against.
    """
    result = await session.execute(
        select(Subscriber, Plan.name, Plan.quota_gb)
        .join(Plan, Plan.id == Subscriber.plan_id)
        .order_by(Subscriber.username)
    )
    pairs = result.all()
    if not pairs:
        return []
    usernames = [sub.username for sub, _, _ in pairs]
    usage_by_username = {u.username: u for u in await summarize_usage(session, usernames=usernames)}
    start, end = month_window()
    rows = []
    for sub, plan_name, quota_gb in pairs:
        usage = usage_by_username.get(sub.username)
        rows.append(
            UsageReportRow(
                subscriber_id=sub.id,
                username=sub.username,
                full_name=sub.full_name,
                plan_id=cast(int, sub.plan_id),
                plan_name=plan_name,
                quota_gb=quota_gb,
                window_start=start,
                window_end=end,
                input_octets=usage.input_octets if usage else 0,
                output_octets=usage.output_octets if usage else 0,
                session_count=usage.session_count if usage else 0,
            )
        )
    return rows
