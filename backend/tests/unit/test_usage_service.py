"""Unit tests for the usage-aggregation service (radacct -> per-subscriber octets)."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update

from app.core.redis import get_redis
from app.models.plan import Plan
from app.models.radius import RadAcct
from app.models.subscriber import Subscriber
from app.services import usage as usage_service
from app.services.usage import month_window, octets_to_gb

# Fixed reference so window math is deterministic regardless of when the suite runs.
WINDOW_START, WINDOW_END = month_window(datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC))


async def _seed_session(
    session,
    *,
    username="bob",
    start=None,
    stop=None,
    in_octets=None,
    out_octets=None,
) -> None:
    session.add(
        RadAcct(
            username=username,
            nasipaddress="192.168.0.10",
            acctstarttime=start or WINDOW_START + timedelta(minutes=1),
            acctstoptime=stop,
            acctsessiontime=3600 if stop else None,
            acctinputoctets=in_octets,
            acctoutputoctets=out_octets,
        )
    )


# --------------------------------------------------------------------------- month_window


async def test_month_window_bounds():
    start, end = month_window(datetime(2026, 8, 15, 23, 59, 59, tzinfo=UTC))
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 9, 1, tzinfo=UTC)


async def test_month_window_is_right_open():
    start, end = month_window(datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC))
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 9, 1, tzinfo=UTC)
    # the final instant of August still belongs to August
    start, end = month_window(datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC))
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 9, 1, tzinfo=UTC)


async def test_month_window_rolls_over_december():
    start, end = month_window(datetime(2026, 12, 25, tzinfo=UTC))
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)


async def test_month_window_treats_naive_reference_as_utc():
    start, end = month_window(datetime(2026, 8, 15))
    assert start == datetime(2026, 8, 1, tzinfo=UTC)
    assert end == datetime(2026, 9, 1, tzinfo=UTC)


async def test_month_window_default_is_current_month():
    start, end = month_window()
    now = datetime.now(UTC)
    assert start <= now < end
    assert start.day == 1 and start.hour == 0 and start.minute == 0
    assert start.tzinfo == UTC


# --------------------------------------------------------------------------- summarize_usage


async def test_summarize_sums_input_output_across_sessions(session):
    await _seed_session(
        session,
        in_octets=100,
        out_octets=200,
        stop=WINDOW_START + timedelta(hours=1),
    )
    # open session, NULL output counter -> coalesces to 0
    await _seed_session(session, in_octets=50, out_octets=None)
    await session.commit()

    rows = await usage_service.summarize_usage(session, start=WINDOW_START, end=WINDOW_END)
    assert len(rows) == 1
    usage = rows[0]
    assert usage.username == "bob"
    assert usage.input_octets == 150
    assert usage.output_octets == 200
    assert usage.total_octets == 350
    assert usage.session_count == 2


async def test_summarize_attributes_to_session_start_month(session):
    # started last month, closed this month -> billed to last month (excluded)
    await _seed_session(
        session,
        in_octets=100,
        out_octets=1,
        start=WINDOW_START - timedelta(days=1),
        stop=WINDOW_START + timedelta(hours=2),
    )
    await _seed_session(session, in_octets=50, out_octets=5)  # this month
    # started next month -> excluded
    await _seed_session(session, in_octets=75, start=WINDOW_END + timedelta(minutes=1))
    await session.commit()

    (usage,) = await usage_service.summarize_usage(session, start=WINDOW_START, end=WINDOW_END)
    assert usage.total_octets == 55
    assert usage.input_octets == 50
    assert usage.session_count == 1


async def test_summarize_groups_by_username_and_filters(session):
    await _seed_session(session, username="bob", in_octets=40)
    await _seed_session(session, username="alice", in_octets=30)
    await session.commit()

    all_rows = await usage_service.summarize_usage(session, start=WINDOW_START, end=WINDOW_END)
    assert [r.username for r in all_rows] == ["alice", "bob"]

    filtered = await usage_service.summarize_usage(
        session, start=WINDOW_START, end=WINDOW_END, usernames=["bob"]
    )
    assert [r.username for r in filtered] == ["bob"]
    assert filtered[0].input_octets == 40


async def test_summarize_empty_when_no_rows_in_window(session):
    # seed before window -> should not appear
    await _seed_session(session, start=WINDOW_START - timedelta(days=5), in_octets=10)
    await session.commit()

    rows = await usage_service.summarize_usage(session, start=WINDOW_START, end=WINDOW_END)
    assert rows == []


# --------------------------------------------------------------------------- get_subscriber_usage


async def test_get_subscriber_usage_zeroed_when_no_sessions(session):
    await session.commit()
    usage = await usage_service.get_subscriber_usage(
        session, "ghost", start=WINDOW_START, end=WINDOW_END
    )
    assert usage.username == "ghost"
    assert usage.total_octets == 0
    assert usage.input_octets == 0
    assert usage.output_octets == 0
    assert usage.session_count == 0
    assert usage.start == WINDOW_START
    assert usage.end == WINDOW_END


async def test_get_subscriber_usage_matches_bulk_summary(session):
    await _seed_session(session, in_octets=60, out_octets=40)
    await session.commit()

    single = await usage_service.get_subscriber_usage(
        session, "bob", start=WINDOW_START, end=WINDOW_END
    )
    (bulk,) = await usage_service.summarize_usage(
        session, start=WINDOW_START, end=WINDOW_END, usernames=["bob"]
    )
    assert single.total_octets == bulk.total_octets == 100
    assert single.session_count == bulk.session_count


# --------------------------------------------------------------------------- Redis cache


async def test_cache_serves_stale_until_cleared(session):
    await _seed_session(session, in_octets=100)
    await session.commit()

    first = await usage_service.get_subscriber_usage(
        session, "bob", start=WINDOW_START, end=WINDOW_END
    )
    assert first.total_octets == 100

    # mutate the DB behind the cache's back -> second read must still be stale
    await session.execute(
        update(RadAcct).where(RadAcct.username == "bob").values(acctinputoctets=700)
    )
    await session.commit()
    cached = await usage_service.get_subscriber_usage(
        session, "bob", start=WINDOW_START, end=WINDOW_END
    )
    assert cached.total_octets == 100  # served from cache, not the DB

    await usage_service.clear_usage_cache()
    fresh = await usage_service.get_subscriber_usage(
        session, "bob", start=WINDOW_START, end=WINDOW_END
    )
    assert fresh.total_octets == 700


async def test_cached_value_written_to_redis_with_ttl(session):
    await _seed_session(session, in_octets=10)
    await session.commit()

    await usage_service.get_subscriber_usage(session, "bob", start=WINDOW_START, end=WINDOW_END)

    redis = get_redis()
    try:
        # Scoped to this worker's prefix: under pytest-xdist a sibling worker
        # may expire its own bob key mid-test, so a cross-worker scan + TTL
        # check is inherently racy.
        keys = [key async for key in redis.scan_iter(f"{usage_service.CACHE_PREFIX}*bob")]
        assert keys, "expected a cached usage key for bob"
        ttl = await redis.ttl(keys[0])
        assert 0 < ttl <= usage_service.CACHE_TTL_SECONDS
        assert "bob" in (await redis.get(keys[0]) or "")
    finally:
        await redis.aclose()


async def test_cache_best_effort_when_redis_unavailable(session, monkeypatch):
    await _seed_session(session, in_octets=10)
    await session.commit()

    def boom() -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(usage_service, "get_redis", boom)

    usage = await usage_service.get_subscriber_usage(
        session, "bob", start=WINDOW_START, end=WINDOW_END
    )
    assert usage.total_octets == 10  # DB fallback despite the outage


# --------------------------------------------------------------------------- usage report


async def _seed_plan(session, name="Starter", quota_gb=100) -> Plan:
    plan = Plan(
        name=name,
        radius_group=f"grp-{name.lower()}",
        price=Decimal("9.99"),
        duration_days=30,
        bandwidth_down_mbps=100,
        bandwidth_up_mbps=10,
        quota_gb=quota_gb,
    )
    session.add(plan)
    return plan


async def _seed_subscriber(session, plan: Plan, username: str) -> None:
    # assign via the relationship so the FK resolves at flush (plan.id is
    # None until then)
    session.add(
        Subscriber(
            username=username,
            full_name=f"{username} Smith",
            status="active",
            plan=plan,
        )
    )


async def test_octets_to_gb_rounds_to_two_decimals():
    assert octets_to_gb(1024**3) == 1.0
    assert octets_to_gb(512 * 1024**2) == 0.5
    assert octets_to_gb(1) == 0.0
    assert octets_to_gb(1500 * 1024**3) == 1500.0


async def test_usage_report_zero_usage_for_silent_subscriber(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, plan, "quiet")
    await session.commit()

    (row,) = await usage_service.get_usage_report(session)
    assert row.username == "quiet"
    assert row.total_octets == 0
    assert row.total_gb == 0.0
    assert row.pct_used == 0
    assert row.session_count == 0
    assert row.quota_gb == 100


async def test_usage_report_matches_aggregation_and_computes_pct(session):
    plan = await _seed_plan(session, quota_gb=10)
    await _seed_subscriber(session, plan, "bob")
    await _seed_session(session, username="bob", in_octets=1024**3, out_octets=1024**3)  # 2 GiB
    await session.commit()

    (row,) = await usage_service.get_usage_report(session)
    assert row.total_gb == 2.0
    assert row.pct_used == 20.0  # 2 / 10 quota
    assert row.plan_name == "Starter"
    assert row.session_count == 1


async def test_usage_report_pct_none_when_plan_has_no_quota(session):
    plan = await _seed_plan(session, name="Unlimited", quota_gb=None)
    await _seed_subscriber(session, plan, "bob")
    await _seed_session(session, username="bob", in_octets=1024**3, out_octets=0)
    await session.commit()

    (row,) = await usage_service.get_usage_report(session)
    assert row.quota_gb is None
    assert row.pct_used is None
    assert row.total_gb == 1.0


async def test_usage_report_excludes_unplanned_subscribers(session):
    plan = await _seed_plan(session)
    await _seed_subscriber(session, plan, "has-plan")
    session.add(Subscriber(username="no-plan", full_name="No Plan", status="active"))
    await session.commit()

    rows = await usage_service.get_usage_report(session)
    assert [r.username for r in rows] == ["has-plan"]


def test_cache_prefix_is_worker_scoped() -> None:
    """The cache prefix (and therefore the per-test clear) is worker-scoped.

    Under pytest-xdist the workers share one Redis but run separate databases,
    so a global namespace would let one worker read or wipe another's live
    cache mid-test (the flake this guards against).
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    assert usage_service.CACHE_PREFIX == (f"usage:{worker}:" if worker else "usage:")


async def test_clear_usage_cache_removes_keys(session):
    # Scoped to this worker's CACHE_PREFIX: under pytest-xdist the workers
    # share one Redis, so other workers' usage:* keys legitimately exist here.
    await _seed_session(session, in_octets=10)
    await session.commit()
    await usage_service.get_subscriber_usage(session, "bob", start=WINDOW_START, end=WINDOW_END)

    redis = get_redis()
    try:
        before = [k async for k in redis.scan_iter(f"{usage_service.CACHE_PREFIX}*")]
        assert before
    finally:
        await redis.aclose()

    await usage_service.clear_usage_cache()

    redis = get_redis()
    try:
        after = [k async for k in redis.scan_iter(f"{usage_service.CACHE_PREFIX}*")]
    finally:
        await redis.aclose()
    assert after == []


# --------------------------------------------------------------------------- monthly_windows


async def test_monthly_windows_spans_year_boundary():
    windows = usage_service.monthly_windows(4, reference=datetime(2026, 1, 15, tzinfo=UTC))
    assert len(windows) == 4
    assert [w[0] for w in windows] == [
        datetime(2025, 10, 1, tzinfo=UTC),
        datetime(2025, 11, 1, tzinfo=UTC),
        datetime(2025, 12, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
    ]
    # right-open: every end is the next start (or the month after the last)
    assert windows[-1][1] == datetime(2026, 2, 1, tzinfo=UTC)
    for start, end in windows:
        assert start < end


async def test_monthly_windows_single_month():
    windows = usage_service.monthly_windows(1, reference=datetime(2026, 8, 15, tzinfo=UTC))
    assert windows == [(datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC))]


async def test_monthly_windows_rejects_zero():
    try:
        usage_service.monthly_windows(0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


# ------------------------------------------------------------------ get_subscriber_usage_history


async def _seed_subscriber_row(session, plan: Plan, username: str) -> Subscriber:
    sub = Subscriber(username=username, full_name=f"{username} Smith", status="active", plan=plan)
    session.add(sub)
    return sub


async def test_usage_history_fills_zero_months(session):
    plan = await _seed_plan(session, quota_gb=100)
    sub = await _seed_subscriber_row(session, plan, "bob")
    await session.commit()

    entries = await usage_service.get_subscriber_usage_history(session, sub, months=3)
    assert len(entries) == 3
    assert all(e.total_octets == 0 and e.session_count == 0 for e in entries)
    assert [e.month for e in entries] == sorted(e.month for e in entries)


async def test_usage_history_aggregates_per_month_and_attributes_by_start(session):
    plan = await _seed_plan(session, quota_gb=100)
    sub = await _seed_subscriber_row(session, plan, "bob")
    await session.commit()

    prev, current = usage_service.monthly_windows(2)
    await _seed_session(
        session,
        username="bob",
        in_octets=1024**3,
        out_octets=0,
        start=current[0] + timedelta(hours=12),
    )
    await _seed_session(
        session,
        username="bob",
        in_octets=512 * 1024**2,
        out_octets=512 * 1024**2,
        start=current[0] + timedelta(days=5),
    )
    # started last month, closed this month -> billed to last month
    await _seed_session(
        session,
        username="bob",
        in_octets=1024**3,
        start=prev[0] + timedelta(hours=6),
        stop=current[0] + timedelta(hours=1),
    )
    await session.commit()

    entries = await usage_service.get_subscriber_usage_history(session, sub, months=2)
    by_month = {e.month: e for e in entries}
    cur = by_month[current[0].strftime("%Y-%m")]
    assert cur.total_octets == 2 * 1024**3  # 1 GiB + (0.5 + 0.5) GiB
    assert cur.session_count == 2
    assert cur.pct_used == 2.0  # 2 GiB of the 100 GiB quota
    assert cur.quota_gb == 100
    assert by_month[prev[0].strftime("%Y-%m")].total_octets == 1024**3
    assert by_month[prev[0].strftime("%Y-%m")].session_count == 1


async def test_usage_history_pct_none_when_plan_has_no_quota(session):
    plan = await _seed_plan(session, name="Unlimited", quota_gb=None)
    sub = await _seed_subscriber_row(session, plan, "bob")
    await session.commit()

    current = usage_service.monthly_windows(1)[-1]
    await _seed_session(
        session, username="bob", in_octets=1024**3, start=current[0] + timedelta(hours=12)
    )
    await session.commit()

    (entry,) = await usage_service.get_subscriber_usage_history(session, sub, months=1)
    assert entry.quota_gb is None
    assert entry.pct_used is None
    assert entry.total_gb == 1.0
