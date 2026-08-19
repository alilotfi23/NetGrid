"""Unit tests for subscriber status-count aggregation (services/subscribers)."""

from app.models.subscriber import Subscriber
from app.services import subscribers as subscribers_service


async def _seed(session, username: str, status: str) -> None:
    session.add(Subscriber(username=username, full_name=username, status=status))
    await session.commit()


async def test_get_subscriber_stats_counts_known_statuses(session):
    await _seed(session, "a1", "active")
    await _seed(session, "a2", "active")
    await _seed(session, "s1", "suspended")
    await _seed(session, "e1", "expired")
    stats = await subscribers_service.get_subscriber_stats(session)
    assert stats == {"active": 2, "suspended": 1, "expired": 1, "total": 4}


async def test_get_subscriber_stats_empty_db(session):
    stats = await subscribers_service.get_subscriber_stats(session)
    assert stats == {"active": 0, "suspended": 0, "expired": 0, "total": 0}


async def test_get_subscriber_stats_unknown_status_not_in_named_counts(session):
    await _seed(session, "x1", "active")
    await _seed(session, "x2", "weird")
    stats = await subscribers_service.get_subscriber_stats(session)
    assert stats["active"] == 1
    assert stats["suspended"] == 0
    assert stats["expired"] == 0
    # drift rows still count toward the total
    assert stats["total"] == 2
