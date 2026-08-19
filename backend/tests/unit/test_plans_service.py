"""Unit tests for the plan service + RADIUS group coupling (services/plans)."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.radius import RadGroupCheck, RadGroupReply
from app.models.rbac import Admin
from app.services import plans as plans_service

RAD_DOWN = plans_service.RAD_DOWN_ATTR
RAD_UP = plans_service.RAD_UP_ATTR
RAD_QUOTA = plans_service.RAD_QUOTA_ATTR


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


async def _reply_rows(session, group: str, attribute: str | None = None) -> list[RadGroupReply]:
    stmt = select(RadGroupReply).where(RadGroupReply.groupname == group)
    if attribute is not None:
        stmt = stmt.where(RadGroupReply.attribute == attribute)
    return list((await session.execute(stmt)).scalars().all())


async def _create_plan(session, actor_id: int, name="Starter", radius_group="rad_starter", **kw):
    defaults = dict(
        price=Decimal("9.99"),
        duration_days=30,
        bandwidth_down_mbps=10,
        bandwidth_up_mbps=5,
        quota_gb=100,
    )
    defaults.update(kw)
    return await plans_service.create_plan(
        session, actor_id=actor_id, name=name, radius_group=radius_group, **defaults
    )


async def test_create_writes_plan_and_group_replies(session):
    actor = await _seed_actor(session)
    plan = await _create_plan(session, actor.id)

    assert plan.radius_group == "rad_starter"
    rows = await _reply_rows(session, "rad_starter")
    assert {r.attribute for r in rows} == {RAD_DOWN, RAD_UP, RAD_QUOTA}
    by_attr = {r.attribute: r.value for r in rows}
    assert by_attr[RAD_DOWN] == "10000"  # 10 Mbps -> kbps
    assert by_attr[RAD_UP] == "5000"  # 5 Mbps -> kbps
    assert by_attr[RAD_QUOTA] == "100000000000"  # 100 GB -> bytes
    assert all(r.op == "=" for r in rows)
    # radgroupcheck stays empty (no check attributes on plans yet)
    checks = (
        (
            await session.execute(
                select(RadGroupCheck).where(RadGroupCheck.groupname == "rad_starter")
            )
        )
        .scalars()
        .all()
    )
    assert checks == []


async def test_create_without_quota_skips_quota_row(session):
    actor = await _seed_actor(session)
    await _create_plan(session, actor.id, quota_gb=None)
    assert await _reply_rows(session, "rad_starter", RAD_QUOTA) == []
    assert len(await _reply_rows(session, "rad_starter")) == 2


async def test_create_duplicate_name_and_group_conflict(session):
    actor = await _seed_actor(session)
    # capture before any rollback: rollback expires session objects, and a
    # later attribute access would trigger a sync lazy-refresh (MissingGreenlet)
    actor_id = actor.id
    await _create_plan(session, actor_id)
    with pytest.raises(ConflictError):
        await _create_plan(session, actor_id)  # same name + group
    with pytest.raises(ConflictError):
        await _create_plan(session, actor_id, name="Other", radius_group="rad_starter")
    with pytest.raises(ConflictError):
        await _create_plan(session, actor_id, name="Starter", radius_group="rad_other")


async def test_get_plan_or_404(session):
    actor = await _seed_actor(session)
    plan = await _create_plan(session, actor.id)
    found = await plans_service.get_plan_or_404(session, plan.id)
    assert found.id == plan.id
    with pytest.raises(NotFoundError):
        await plans_service.get_plan_or_404(session, 999)


async def test_list_plans_paginates_and_filters(session):
    actor = await _seed_actor(session)
    for i in range(3):
        await _create_plan(session, actor.id, name=f"P{i}", radius_group=f"rad_p{i}")
    page1, total = await plans_service.list_plans(session, page=1, page_size=2)
    assert len(page1) == 2
    assert total == 3
    filtered, total = await plans_service.list_plans(session, page=1, page_size=20, q="P1")
    assert [p.name for p in filtered] == ["P1"]
    assert total == 1


async def test_update_bandwidth_resyncs_group_replies(session):
    actor = await _seed_actor(session)
    plan = await _create_plan(session, actor.id)
    updated = await plans_service.update_plan(
        session, plan, actor_id=actor.id, bandwidth_down_mbps=20
    )
    assert updated.bandwidth_down_mbps == 20
    down = await _reply_rows(session, "rad_starter", RAD_DOWN)
    assert len(down) == 1  # re-synced, not duplicated
    assert down[0].value == "20000"
    # untouched attributes survive the re-sync
    assert (await _reply_rows(session, "rad_starter", RAD_UP))[0].value == "5000"


async def test_update_noop_skips_commit_and_audit(session):
    actor = await _seed_actor(session)
    plan = await _create_plan(session, actor.id, description="desc")
    await plans_service.update_plan(session, plan, actor_id=actor.id, description="desc")
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert [e.action for e in rows] == ["create"]


async def test_update_writes_audit_entry(session):
    actor = await _seed_actor(session)
    plan = await _create_plan(session, actor.id)
    await plans_service.update_plan(
        session, plan, actor_id=actor.id, price=Decimal("12.50"), is_active=False
    )
    rows = (await session.execute(select(AuditLog))).scalars().all()
    update = next(e for e in rows if e.action == "update")
    assert update.resource == "plans"
    assert update.metadata_ == {"name": "Starter", "fields": ["price", "is_active"]}
