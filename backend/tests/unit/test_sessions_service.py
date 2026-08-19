"""Unit tests for the live-sessions service (Phase 9 read side)."""

from datetime import UTC, datetime, timedelta

from app.models.radius import Nas, RadAcct
from app.models.subscriber import Subscriber
from app.services import sessions as sessions_service


def _seed_session(
    session,
    *,
    username="bob",
    nas="192.168.0.10",
    start=None,
    stop=None,
    framed="10.0.0.5",
    duration=3600,
    rx=1024,
    tx=2048,
) -> RadAcct:
    row = RadAcct(
        username=username,
        nasipaddress=nas,
        acctstarttime=start or datetime.now(UTC) - timedelta(minutes=30),
        acctstoptime=stop,
        acctsessiontime=duration,
        acctinputoctets=rx,
        acctoutputoctets=tx,
        framedipaddress=framed,
    )
    session.add(row)
    return row


async def test_list_live_sessions_returns_only_open_sessions(session):
    _seed_session(session, username="bob", nas="192.168.0.10")
    _seed_session(
        session,
        username="alice",
        nas="192.168.0.11",
        stop=datetime.now(UTC),  # closed session
    )
    await session.commit()

    items, total = await sessions_service.list_live_sessions(session, page=1, page_size=20)
    assert total == 1
    assert len(items) == 1
    assert items[0]["username"] == "bob"
    assert items[0]["nasipaddress"] == "192.168.0.10"
    assert items[0]["nas_shortname"] is None  # no nas-table row for the IP
    assert items[0]["framedipaddress"] == "10.0.0.5"


async def test_list_live_sessions_newest_first_and_paginates(session):
    old = _seed_session(session, username="bob", start=datetime.now(UTC) - timedelta(hours=2))
    new = _seed_session(session, username="alice", start=datetime.now(UTC) - timedelta(minutes=5))
    await session.commit()

    items, total = await sessions_service.list_live_sessions(session, page=1, page_size=20)
    assert [i["id"] for i in items] == [new.id, old.id]

    items, total = await sessions_service.list_live_sessions(session, page=2, page_size=1)
    assert len(items) == 1
    assert total == 2


async def test_list_live_sessions_resolves_subscriber_id(session):
    session.add(Subscriber(username="bob", full_name="Bob", status="active"))
    _seed_session(session, username="bob", nas="192.168.0.10")
    _seed_session(session, username="alice", nas="192.168.0.11")  # no subscriber row
    await session.commit()

    items, total = await sessions_service.list_live_sessions(session, 1, 20)
    assert total == 2
    by_username = {item["username"]: item["subscriber_id"] for item in items}
    assert by_username["bob"] is not None
    assert by_username["alice"] is None


async def test_list_live_sessions_filters_by_username_or_nas(session):
    _seed_session(session, username="bob", nas="192.168.0.10")
    _seed_session(session, username="alice", nas="192.168.0.11")
    await session.commit()

    by_user, total = await sessions_service.list_live_sessions(session, 1, 20, q="bo")
    assert total == 1
    assert by_user[0]["username"] == "bob"

    by_nas, total = await sessions_service.list_live_sessions(session, 1, 20, q="192.168.0.11")
    assert total == 1
    assert by_nas[0]["username"] == "alice"


async def test_list_live_sessions_resolves_nas_shortname(session):
    session.add(Nas(nasname="192.168.0.10", shortname="edge-r1", type="mikrotik", secret="x"))
    _seed_session(session, username="bob", nas="192.168.0.10")
    _seed_session(session, username="alice", nas="192.168.0.11")  # no nas row
    await session.commit()

    items, total = await sessions_service.list_live_sessions(session, 1, 20)
    assert total == 2
    by_ip = {item["nasipaddress"]: item["nas_shortname"] for item in items}
    assert by_ip == {"192.168.0.10": "edge-r1", "192.168.0.11": None}

    # q matches the shortname too
    by_shortname, total = await sessions_service.list_live_sessions(session, 1, 20, q="edge-r1")
    assert total == 1
    assert by_shortname[0]["username"] == "bob"


async def test_live_session_stats_groups_by_nas(session):
    _seed_session(session, username="bob", nas="192.168.0.10")
    _seed_session(session, username="carol", nas="192.168.0.10")
    _seed_session(session, username="alice", nas="192.168.0.11")
    _seed_session(
        session,
        username="dave",
        nas="192.168.0.12",
        stop=datetime.now(UTC),  # closed — excluded
    )
    await session.commit()

    total, by_nas = await sessions_service.get_live_session_stats(session)
    assert total == 3
    # sorted by count descending, then IP; no nas rows -> shortname None
    assert by_nas == [("192.168.0.10", 2, None), ("192.168.0.11", 1, None)]


async def test_live_session_stats_resolves_nas_shortname(session):
    session.add(Nas(nasname="192.168.0.10", shortname="edge-r1", type="mikrotik", secret="x"))
    _seed_session(session, username="bob", nas="192.168.0.10")
    _seed_session(session, username="carol", nas="192.168.0.10")
    _seed_session(session, username="alice", nas="192.168.0.11")
    await session.commit()

    total, by_nas = await sessions_service.get_live_session_stats(session)
    assert total == 3
    assert by_nas == [("192.168.0.10", 2, "edge-r1"), ("192.168.0.11", 1, None)]


async def test_live_session_stats_empty(session):
    total, by_nas = await sessions_service.get_live_session_stats(session)
    assert total == 0
    assert by_nas == []
