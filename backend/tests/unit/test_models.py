import pytest
from sqlalchemy.exc import IntegrityError

from app.models.nas import NasDevice
from app.models.plan import Plan
from app.models.rbac import Admin, Permission, Role
from app.models.subscriber import Subscriber


async def test_admin_username_must_be_unique(session):
    session.add(Admin(username="root", email="root@netgrid.local", password_hash="x"))
    await session.commit()
    session.add(Admin(username="root", email="other@netgrid.local", password_hash="x"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_admin_required_fields(session):
    session.add(Admin(username="root", email="root@netgrid.local", password_hash=None))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_subscriber_username_must_be_unique(session):
    session.add(Subscriber(username="alice", full_name="Alice A"))
    await session.commit()
    session.add(Subscriber(username="alice", full_name="Alice B"))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_plan_name_and_radius_group_must_be_unique(session):
    session.add(
        Plan(
            name="Home 20",
            radius_group="home20",
            price=20,
            duration_days=30,
            bandwidth_down_mbps=20,
            bandwidth_up_mbps=5,
        )
    )
    await session.commit()
    session.add(
        Plan(
            name="Home 20",
            radius_group="home20b",
            price=25,
            duration_days=30,
            bandwidth_down_mbps=25,
            bandwidth_up_mbps=5,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_nas_ip_address_must_be_unique(session):
    session.add(
        NasDevice(name="rtr1", ip_address="10.0.0.1", shortname="rtr1", secret_encrypted="enc:abc")
    )
    await session.commit()
    session.add(
        NasDevice(name="rtr2", ip_address="10.0.0.1", shortname="rtr2", secret_encrypted="enc:def")
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_role_permission_many_to_many(session):
    role = Role(name="super_admin")
    role.permissions.append(Permission(code="subscribers:write"))
    session.add(role)
    await session.commit()
    assert role.permissions[0].code == "subscribers:write"
