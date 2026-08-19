"""Unit tests for the NAS device service + FreeRADIUS nas coupling."""

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret, hash_password
from app.models.audit import AuditLog
from app.models.nas import NasDevice
from app.models.radius import Nas
from app.models.rbac import Admin
from app.services import nas_devices as nas_service


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


async def _create(session, actor_id: int, name="core-r1", ip="192.168.0.10", **kw):
    defaults = dict(
        shortname="core1",
        secret="radius_secret_1",
        nas_type="other",
        ports=1812,
        server="radius.internal",
        community="public",
        description="Core router",
    )
    defaults.update(kw)
    return await nas_service.create_nas_device(
        session, actor_id=actor_id, name=name, ip_address=ip, **defaults
    )


async def _nas_row(session, ip_address: str) -> Nas | None:
    return (
        await session.execute(select(Nas).where(Nas.nasname == ip_address))
    ).scalar_one_or_none()


async def test_create_writes_inventory_and_nas_row(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)

    # the inventory row stores the Fernet-encrypted secret, never plaintext
    assert device.secret_encrypted != "radius_secret_1"
    assert decrypt_secret(device.secret_encrypted) == "radius_secret_1"

    # the FreeRADIUS nas row carries the plaintext secret FreeRADIUS needs
    row = await _nas_row(session, "192.168.0.10")
    assert row is not None
    assert row.nasname == "192.168.0.10"
    assert row.shortname == "core1"
    assert row.type == "other"
    assert row.ports == 1812
    assert row.secret == "radius_secret_1"
    assert row.server == "radius.internal"
    assert row.community == "public"
    assert row.description == "Core router"


async def test_create_inactive_writes_no_nas_row(session):
    actor = await _seed_actor(session)
    await _create(session, actor.id, is_active=False)
    assert await _nas_row(session, "192.168.0.10") is None


async def test_create_duplicate_name_or_ip_conflict(session):
    actor = await _seed_actor(session)
    actor_id = actor.id
    await _create(session, actor_id)
    with pytest.raises(ConflictError):
        await _create(session, actor_id)  # same name + ip
    with pytest.raises(ConflictError):
        await _create(session, actor_id, name="other", ip="192.168.0.10")
    with pytest.raises(ConflictError):
        await _create(session, actor_id, name="core-r1", ip="10.0.0.1")


async def test_get_nas_device_or_404(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)
    found = await nas_service.get_nas_device_or_404(session, device.id)
    assert found.id == device.id
    with pytest.raises(NotFoundError):
        await nas_service.get_nas_device_or_404(session, 999)


async def test_list_nas_devices_paginates_and_filters(session):
    actor = await _seed_actor(session)
    for i in range(3):
        await _create(session, actor.id, name=f"r{i}", ip=f"192.168.0.{i + 1}")
    page1, total = await nas_service.list_nas_devices(session, page=1, page_size=2)
    assert len(page1) == 2
    assert total == 3
    filtered, total = await nas_service.list_nas_devices(session, page=1, page_size=20, q="r1")
    assert [d.name for d in filtered] == ["r1"]
    assert total == 1
    filtered, total = await nas_service.list_nas_devices(
        session, page=1, page_size=20, q="192.168.0.2"
    )
    assert [d.name for d in filtered] == ["r1"]


async def test_update_secret_rotates_nas_row(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)
    await nas_service.update_nas_device(session, device, actor_id=actor.id, secret="new_secret_9")
    assert decrypt_secret(device.secret_encrypted) == "new_secret_9"
    row = await _nas_row(session, "192.168.0.10")
    assert row is not None
    assert row.secret == "new_secret_9"


async def test_update_fields_sync_nas_row(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)
    await nas_service.update_nas_device(
        session, device, actor_id=actor.id, shortname="edge1", ports=3799
    )
    row = await _nas_row(session, "192.168.0.10")
    assert row is not None
    assert row.shortname == "edge1"
    assert row.ports == 3799


async def test_deactivate_removes_nas_row_reactivate_recreates(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)
    assert await _nas_row(session, "192.168.0.10") is not None

    await nas_service.update_nas_device(session, device, actor_id=actor.id, is_active=False)
    assert await _nas_row(session, "192.168.0.10") is None

    # reactivating decrypts the stored secret and recreates the nas row
    await nas_service.update_nas_device(session, device, actor_id=actor.id, is_active=True)
    row = await _nas_row(session, "192.168.0.10")
    assert row is not None
    assert row.secret == "radius_secret_1"


async def test_delete_removes_inventory_and_nas_row(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)
    device_id = device.id
    await nas_service.delete_nas_device(session, device, actor.id)

    assert (
        await session.execute(select(NasDevice).where(NasDevice.id == device_id))
    ).scalar_one_or_none() is None
    assert await _nas_row(session, "192.168.0.10") is None


async def test_audit_entries_written(session):
    actor = await _seed_actor(session)
    device = await _create(session, actor.id)
    await nas_service.update_nas_device(session, device, actor_id=actor.id, secret="rotated_1")
    await nas_service.delete_nas_device(session, device, actor.id)

    rows = (await session.execute(select(AuditLog))).scalars().all()
    actions = {(row.action, row.resource) for row in rows}
    assert actions == {
        ("create", "nas_devices"),
        ("update", "nas_devices"),
        ("delete", "nas_devices"),
    }
    update = next(r for r in rows if r.action == "update")
    assert update.metadata_ == {"name": "core-r1", "fields": ["secret"]}


async def test_encrypt_decrypt_roundtrip():
    assert encrypt_secret("s3cret!") != "s3cret!"
    assert decrypt_secret(encrypt_secret("s3cret!")) == "s3cret!"
