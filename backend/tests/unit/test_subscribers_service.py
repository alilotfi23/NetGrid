"""Unit tests for the subscriber service (services/subscribers)."""

from datetime import UTC
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.plan import Plan
from app.models.radius import RadAcct, RadCheck, RadUserGroup
from app.models.rbac import Admin
from app.models.subscriber import Subscriber
from app.services import subscribers as subscribers_service

RAD_PASSWORD_ATTRIBUTE = subscribers_service.RAD_PASSWORD_ATTRIBUTE
RAD_AUTH_TYPE_ATTRIBUTE = subscribers_service.RAD_AUTH_TYPE_ATTRIBUTE


async def _radcheck_rows(session, username: str, attribute: str | None = None) -> list[RadCheck]:
    stmt = select(RadCheck).where(RadCheck.username == username)
    if attribute is not None:
        stmt = stmt.where(RadCheck.attribute == attribute)
    return list((await session.execute(stmt)).scalars().all())


async def _seed_actor(session, username="actor") -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    return admin


async def _seed(session, username: str, status: str, plan_id: int | None = None) -> None:
    session.add(Subscriber(username=username, full_name=username, status=status, plan_id=plan_id))
    await session.commit()


async def _seed_plan(session, name: str) -> Plan:
    plan = Plan(
        name=name,
        radius_group=f"rad_{name.lower()}",
        price=Decimal("9.99"),
        duration_days=30,
        bandwidth_down_mbps=10,
        bandwidth_up_mbps=5,
    )
    session.add(plan)
    await session.commit()
    return plan


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


async def test_get_subscriber_plan_counts(session):
    p1 = await _seed_plan(session, "Starter")
    p2 = await _seed_plan(session, "Pro")
    await _seed(session, "a1", "active", plan_id=p1.id)
    await _seed(session, "a2", "active", plan_id=p1.id)
    await _seed(session, "s1", "suspended", plan_id=p2.id)
    await _seed(session, "u1", "active")  # no plan

    counts = await subscribers_service.get_subscriber_plan_counts(session)
    assert counts == [
        {"plan_id": p1.id, "plan_name": "Starter", "count": 2},
        {"plan_id": p2.id, "plan_name": "Pro", "count": 1},
        {"plan_id": None, "plan_name": None, "count": 1},
    ]


async def test_get_subscriber_plan_counts_empty_db(session):
    assert await subscribers_service.get_subscriber_plan_counts(session) == []


async def test_get_subscriber_plan_status_counts(session):
    p1 = await _seed_plan(session, "Starter")
    await _seed(session, "a1", "active", plan_id=p1.id)
    await _seed(session, "a2", "suspended", plan_id=p1.id)
    await _seed(session, "e1", "expired")  # unassigned

    matrix = await subscribers_service.get_subscriber_plan_status_counts(session)
    assert matrix == [
        {"plan_id": p1.id, "plan_name": "Starter", "status": "active", "count": 1},
        {"plan_id": p1.id, "plan_name": "Starter", "status": "suspended", "count": 1},
        {"plan_id": None, "plan_name": None, "status": "expired", "count": 1},
    ]


async def test_get_subscriber_plan_status_counts_empty_db(session):
    assert await subscribers_service.get_subscriber_plan_status_counts(session) == []


async def test_create_writes_profile_and_radius_password(session):
    actor = await _seed_actor(session)
    subscriber = await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob Subscriber",
        password="radpass123",
    )
    assert subscriber.username == "bob"
    assert subscriber.status == "active"

    rows = await _radcheck_rows(session, "bob")
    assert len(rows) == 1
    assert rows[0].attribute == RAD_PASSWORD_ATTRIBUTE
    assert rows[0].op == ":="
    assert rows[0].value == "radpass123"


async def test_create_suspended_writes_reject(session):
    actor = await _seed_actor(session)
    await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob",
        password="radpass123",
        status="suspended",
    )
    rows = await _radcheck_rows(session, "bob")
    assert {r.attribute for r in rows} == {RAD_PASSWORD_ATTRIBUTE, RAD_AUTH_TYPE_ATTRIBUTE}
    reject = next(r for r in rows if r.attribute == RAD_AUTH_TYPE_ATTRIBUTE)
    assert reject.value == "Reject"


async def test_create_duplicate_username_conflict(session):
    actor = await _seed_actor(session)
    kwargs = dict(actor_id=actor.id, username="bob", full_name="Bob", password="radpass123")
    await subscribers_service.create_subscriber(session, **kwargs)
    with pytest.raises(ConflictError):
        await subscribers_service.create_subscriber(session, **kwargs)
    # the failed create's radcheck rows were rolled back with it
    assert len(await _radcheck_rows(session, "bob")) == 1


async def test_get_subscriber_or_404(session):
    actor = await _seed_actor(session)
    subscriber = await subscribers_service.create_subscriber(
        session, actor_id=actor.id, username="bob", full_name="Bob", password="radpass123"
    )
    found = await subscribers_service.get_subscriber_or_404(session, subscriber.id)
    assert found.id == subscriber.id
    with pytest.raises(NotFoundError):
        await subscribers_service.get_subscriber_or_404(session, 999)


async def test_list_subscribers_paginates_and_filters(session):
    actor = await _seed_actor(session)
    for i in range(3):
        await subscribers_service.create_subscriber(
            session,
            actor_id=actor.id,
            username=f"u{i}",
            full_name=f"User {i}",
            password="radpass123",
        )
    page1, total = await subscribers_service.list_subscribers(session, page=1, page_size=2)
    assert len(page1) == 2
    assert total == 3
    filtered, total = await subscribers_service.list_subscribers(
        session, page=1, page_size=20, q="u1"
    )
    assert [s.username for s in filtered] == ["u1"]
    assert total == 1


async def test_list_subscribers_filters_by_plan(session):
    p1 = await _seed_plan(session, "Starter")
    await _seed(session, "a1", "active", plan_id=p1.id)
    await _seed(session, "a2", "active", plan_id=p1.id)
    await _seed(session, "u1", "active")  # no plan

    assigned, total = await subscribers_service.list_subscribers(
        session, page=1, page_size=20, plan_id=p1.id
    )
    assert total == 2
    assert {s.username for s in assigned} == {"a1", "a2"}

    unassigned, total = await subscribers_service.list_subscribers(
        session, page=1, page_size=20, no_plan=True
    )
    assert total == 1
    assert [s.username for s in unassigned] == ["u1"]


async def test_create_writes_audit_entry(session):
    actor = await _seed_actor(session)
    await subscribers_service.create_subscriber(
        session, actor_id=actor.id, username="bob", full_name="Bob", password="radpass123"
    )
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert any(
        e.action == "create" and e.resource == "subscribers" and e.admin_id == actor.id
        for e in rows
    )


async def _create(session, username="bob", status="active") -> Subscriber:
    actor = await _seed_actor(session)
    return await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username=username,
        full_name="Bob",
        password="radpass123",
        status=status,
    )


async def test_update_password_upserts_radius_row(session):
    subscriber = await _create(session)
    actor = await _seed_actor(session, "actor2")
    updated = await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, password="newpass456"
    )
    assert updated.username == "bob"
    rows = await _radcheck_rows(session, "bob", RAD_PASSWORD_ATTRIBUTE)
    assert len(rows) == 1  # upserted, not duplicated
    assert rows[0].value == "newpass456"


async def test_update_status_syncs_reject(session):
    subscriber = await _create(session)  # active -> no reject row
    actor = await _seed_actor(session, "actor2")
    assert len(await _radcheck_rows(session, "bob", RAD_AUTH_TYPE_ATTRIBUTE)) == 0

    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, status="suspended"
    )
    reject = await _radcheck_rows(session, "bob", RAD_AUTH_TYPE_ATTRIBUTE)
    assert len(reject) == 1
    assert reject[0].value == "Reject"

    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, status="active"
    )
    assert len(await _radcheck_rows(session, "bob", RAD_AUTH_TYPE_ATTRIBUTE)) == 0


async def test_update_profile_fields_leave_radius_untouched(session):
    subscriber = await _create(session)
    actor = await _seed_actor(session, "actor2")
    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, full_name="Robert", email="r@netgrid.local"
    )
    assert subscriber.full_name == "Robert"
    rows = await _radcheck_rows(session, "bob")
    assert {r.attribute for r in rows} == {RAD_PASSWORD_ATTRIBUTE}


async def test_delete_removes_profile_and_radius_rows(session):
    subscriber = await _create(session, status="suspended")  # 2 radcheck rows
    actor = await _seed_actor(session, "actor2")
    subscriber_id = subscriber.id
    await subscribers_service.delete_subscriber(session, subscriber, actor.id)

    assert (
        await session.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    ).scalar_one_or_none() is None
    assert await _radcheck_rows(session, "bob") == []
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert any(
        e.action == "delete" and e.resource == "subscribers" and e.resource_id == str(subscriber_id)
        for e in rows
    )


async def _radusergroup_rows(session, username: str) -> list[RadUserGroup]:
    return list(
        (await session.execute(select(RadUserGroup).where(RadUserGroup.username == username)))
        .scalars()
        .all()
    )


async def test_create_with_plan_writes_radusergroup(session):
    actor = await _seed_actor(session)
    plan = await _seed_plan(session, "Starter")
    subscriber = await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob",
        password="radpass123",
        plan_id=plan.id,
    )
    assert subscriber.plan_id == plan.id
    memberships = await _radusergroup_rows(session, "bob")
    assert len(memberships) == 1
    assert memberships[0].groupname == plan.radius_group
    assert memberships[0].priority == 1


async def test_create_with_unknown_plan_404(session):
    actor = await _seed_actor(session)
    with pytest.raises(NotFoundError):
        await subscribers_service.create_subscriber(
            session,
            actor_id=actor.id,
            username="bob",
            full_name="Bob",
            password="radpass123",
            plan_id=999,
        )


async def test_update_plan_switches_membership(session):
    actor = await _seed_actor(session)
    p1 = await _seed_plan(session, "Starter")
    p2 = await _seed_plan(session, "Pro")
    subscriber = await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob",
        password="radpass123",
        plan_id=p1.id,
    )

    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, plan_id=p2.id
    )
    assert subscriber.plan_id == p2.id
    memberships = await _radusergroup_rows(session, "bob")
    assert [m.groupname for m in memberships] == [p2.radius_group]


async def test_update_plan_clear_removes_membership(session):
    actor = await _seed_actor(session)
    plan = await _seed_plan(session, "Starter")
    subscriber = await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob",
        password="radpass123",
        plan_id=plan.id,
    )

    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, plan_id=None
    )
    assert subscriber.plan_id is None
    assert await _radusergroup_rows(session, "bob") == []


async def test_update_plan_unknown_404_leaves_membership_untouched(session):
    actor = await _seed_actor(session)
    plan = await _seed_plan(session, "Starter")
    subscriber = await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob",
        password="radpass123",
        plan_id=plan.id,
    )
    with pytest.raises(NotFoundError):
        await subscribers_service.update_subscriber(
            session, subscriber, actor_id=actor.id, plan_id=999
        )
    # validation happens before the membership swap, so nothing was torn down
    memberships = await _radusergroup_rows(session, "bob")
    assert [m.groupname for m in memberships] == [plan.radius_group]


async def test_delete_removes_radusergroup(session):
    actor = await _seed_actor(session)
    plan = await _seed_plan(session, "Starter")
    subscriber = await subscribers_service.create_subscriber(
        session,
        actor_id=actor.id,
        username="bob",
        full_name="Bob",
        password="radpass123",
        plan_id=plan.id,
    )
    await subscribers_service.delete_subscriber(session, subscriber, actor.id)
    assert await _radusergroup_rows(session, "bob") == []


async def test_history_lists_events_newest_first_with_status_transition(session):
    subscriber = await _create(session)
    actor = await _seed_actor(session, "actor2")
    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, status="suspended"
    )

    history = await subscribers_service.list_subscriber_history(session, subscriber.id)
    # create event first (oldest), then the status update
    assert [e.action for e in history] == ["update", "create"]
    update_event = history[0]
    assert update_event.metadata_["status_from"] == "active"
    assert update_event.metadata_["status_to"] == "suspended"
    assert update_event.metadata_["fields"] == ["status"]


async def test_history_only_includes_this_subscriber(session):
    actor = await _seed_actor(session)
    s1 = await subscribers_service.create_subscriber(
        session, actor_id=actor.id, username="bob", full_name="Bob", password="radpass123"
    )
    s2 = await subscribers_service.create_subscriber(
        session, actor_id=actor.id, username="alice", full_name="Alice", password="radpass123"
    )
    await subscribers_service.update_subscriber(
        session, s2, actor_id=actor.id, full_name="Alice A."
    )

    history = await subscribers_service.list_subscriber_history(session, s1.id)
    assert [e.action for e in history] == ["create"]


async def _seed_session(session, username: str, *, open_: bool = True) -> RadAcct:
    from datetime import datetime

    row = RadAcct(
        username=username,
        nasipaddress="192.168.0.10",
        acctstarttime=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        acctstoptime=None if open_ else datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
        acctsessiontime=3600,
        acctinputoctets=1048576,
        acctoutputoctets=2097152,
        framedipaddress="10.0.0.5",
    )
    session.add(row)
    await session.commit()
    return row


async def test_live_sessions_returns_open_sessions_for_username(session):
    await _seed_session(session, "bob")
    await _seed_session(session, "bob")
    await _seed_session(session, "alice")

    sessions = await subscribers_service.get_live_sessions(session, "bob")
    assert len(sessions) == 2
    for s in sessions:
        assert s["username"] == "bob"
        # inet columns surface as plain strings for JSON serialization
        assert s["nasipaddress"] == "192.168.0.10"
        assert s["framedipaddress"] == "10.0.0.5"
        assert s["acctsessiontime"] == 3600


async def test_live_sessions_excludes_closed_sessions(session):
    await _seed_session(session, "bob", open_=False)
    assert await subscribers_service.get_live_sessions(session, "bob") == []
