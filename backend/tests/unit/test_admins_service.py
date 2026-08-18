import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.audit import AuditLog
from app.models.rbac import Admin, Permission, Role, admin_roles
from app.services import admins as admins_service


async def _reload_with_roles(session, admin_id: int) -> Admin:
    """Re-fetch with roles eagerly loaded so appends don't lazy-load (async)."""
    return (
        await session.execute(
            select(Admin).options(selectinload(Admin.roles)).where(Admin.id == admin_id)
        )
    ).scalar_one()


async def _ensure_permissions(session, *codes: str) -> None:
    """Create permission rows the catalog validation requires."""
    existing = set((await session.execute(select(Permission.code))).scalars().all())
    for code in codes:
        if code not in existing:
            session.add(Permission(code=code))
    await session.commit()


async def _seed_admin(session, username="alice", role_codes=None) -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    for codes in role_codes or []:
        role = Role(name=f"{username}_role_{len(admin.roles)}")
        role.permissions = [Permission(code=code) for code in codes]
        admin.roles.append(role)
    session.add(admin)
    await session.commit()
    return admin


async def _seed_role(session, name="support", codes=None) -> Role:
    role = Role(name=name)
    role.permissions = [Permission(code=code) for code in codes or []]
    session.add(role)
    await session.commit()
    return role


# ---------------------------------------------------------------------------
# create_admin
# ---------------------------------------------------------------------------


async def test_create_admin_hashes_password_and_assigns_roles(session):
    role = await _seed_role(session, "support", ["subscribers:read"])
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    admin = await admins_service.create_admin(
        session,
        username="bob",
        email="bob@netgrid.local",
        password="secret123",
        is_active=True,
        role_ids=[role.id],
        actor_id=actor.id,
    )
    assert admin.username == "bob"
    assert admin.password_hash != "secret123"
    assert verify_password("secret123", admin.password_hash)
    assert [r.id for r in admin.roles] == [role.id]


async def test_create_admin_duplicate_username_conflict(session):
    await _seed_admin(session, "bob")
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    with pytest.raises(ConflictError):
        await admins_service.create_admin(
            session,
            username="bob",
            email="other@netgrid.local",
            password="secret123",
            is_active=True,
            role_ids=[],
            actor_id=actor.id,
        )


async def test_create_admin_unknown_role_not_found(session):
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    with pytest.raises(NotFoundError):
        await admins_service.create_admin(
            session,
            username="bob",
            email="bob@netgrid.local",
            password="secret123",
            is_active=True,
            role_ids=[999],
            actor_id=actor.id,
        )


# ---------------------------------------------------------------------------
# update_admin
# ---------------------------------------------------------------------------


async def test_update_admin_changes_fields(session):
    admin = await _seed_admin(session, "bob")
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    updated = await admins_service.update_admin(
        session, admin, actor_id=actor.id, email="new@netgrid.local", password="newpass123"
    )
    assert updated.email == "new@netgrid.local"
    assert verify_password("newpass123", updated.password_hash)
    assert not verify_password("secret123", updated.password_hash)


async def test_update_admin_cannot_deactivate_self(session):
    admin = await _seed_admin(session, "bob", [["admins:manage"]])
    with pytest.raises(BadRequestError):
        await admins_service.update_admin(session, admin, actor_id=admin.id, is_active=False)


async def test_update_admin_can_deactivate_other(session):
    target = await _seed_admin(session, "target")
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    updated = await admins_service.update_admin(session, target, actor_id=actor.id, is_active=False)
    assert updated.is_active is False


# ---------------------------------------------------------------------------
# set_admin_roles
# ---------------------------------------------------------------------------


async def test_set_admin_roles_replaces_and_invalidates(session, monkeypatch):
    target = await _seed_admin(session, "target", [["plans:read"]])
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    role = await _seed_role(session, "support", ["subscribers:read"])
    invalidated: list[int] = []

    async def fake_invalidate(admin_id: int) -> None:
        invalidated.append(admin_id)

    monkeypatch.setattr(admins_service, "invalidate_admin_permissions", fake_invalidate)
    await admins_service.set_admin_roles(session, target, [role.id], actor.id)
    assert invalidated == [target.id]
    assert [r.id for r in target.roles] == [role.id]


async def test_set_admin_roles_cannot_change_own(session):
    admin = await _seed_admin(session, "bob", [["admins:manage"]])
    with pytest.raises(BadRequestError):
        await admins_service.set_admin_roles(session, admin, [], admin.id)


async def test_set_admin_roles_unknown_role_not_found(session):
    target = await _seed_admin(session, "target")
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    with pytest.raises(NotFoundError):
        await admins_service.set_admin_roles(session, target, [999], actor.id)


# ---------------------------------------------------------------------------
# create_role / update_role
# ---------------------------------------------------------------------------


async def test_create_role_with_permissions(session):
    await _ensure_permissions(session, "subscribers:read")
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    role = await admins_service.create_role(
        session,
        name="support",
        description="Frontline",
        permission_codes=["subscribers:read"],
        actor_id=actor.id,
    )
    assert role.name == "support"
    assert [p.code for p in role.permissions] == ["subscribers:read"]


async def test_create_role_duplicate_name_conflict(session):
    await _seed_role(session, "support")
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    with pytest.raises(ConflictError):
        await admins_service.create_role(
            session, name="support", description=None, permission_codes=[], actor_id=actor.id
        )


async def test_create_role_unknown_permission_not_found(session):
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    with pytest.raises(NotFoundError):
        await admins_service.create_role(
            session,
            name="support",
            description=None,
            permission_codes=["nope:read"],
            actor_id=actor.id,
        )


async def test_update_role_renames(session):
    role = await _seed_role(session, "support")
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    updated = await admins_service.update_role(session, role, actor_id=actor.id, name="support2")
    assert updated.name == "support2"


# ---------------------------------------------------------------------------
# set_role_permissions
# ---------------------------------------------------------------------------


async def test_set_role_permissions_replaces_and_invalidates_members(session, monkeypatch):
    await _ensure_permissions(session, "plans:read")
    role = await _seed_role(session, "support", ["subscribers:read"])
    member1 = await _reload_with_roles(session, (await _seed_admin(session, "m1")).id)
    member2 = await _reload_with_roles(session, (await _seed_admin(session, "m2")).id)
    member1.roles.append(role)
    member2.roles.append(role)
    await session.commit()
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    invalidated: list[int] = []

    async def fake_invalidate(admin_id: int) -> None:
        invalidated.append(admin_id)

    monkeypatch.setattr(admins_service, "invalidate_admin_permissions", fake_invalidate)
    await admins_service.set_role_permissions(session, role, ["plans:read"], actor.id)
    assert sorted(invalidated) == sorted([member1.id, member2.id])
    assert [p.code for p in role.permissions] == ["plans:read"]


async def test_set_role_permissions_unknown_permission_not_found(session):
    role = await _seed_role(session, "support")
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    with pytest.raises(NotFoundError):
        await admins_service.set_role_permissions(session, role, ["nope:read"], actor.id)


async def test_set_role_permissions_self_manage_guard(session):
    # the actor's only role grants *:*; stripping it would lock them out
    await _ensure_permissions(session, "subscribers:read")
    actor = await _seed_admin(session, "actor", [["*:*"]])
    role = actor.roles[0]
    with pytest.raises(BadRequestError):
        await admins_service.set_role_permissions(session, role, ["subscribers:read"], actor.id)


async def test_set_role_permissions_allowed_when_manage_kept_elsewhere(session):
    await _ensure_permissions(session, "subscribers:read")
    actor = await _seed_admin(session, "actor", [["*:*"], ["admins:manage"]])
    role = actor.roles[0]  # the *:* role
    updated = await admins_service.set_role_permissions(
        session, role, ["subscribers:read"], actor.id
    )
    assert [p.code for p in updated.permissions] == ["subscribers:read"]


# ---------------------------------------------------------------------------
# delete_admin
# ---------------------------------------------------------------------------


async def test_delete_admin_removes_row_and_role_links(session, monkeypatch):
    role = await _seed_role(session, "support", ["subscribers:read"])
    target = await _reload_with_roles(session, (await _seed_admin(session, "doomed")).id)
    target.roles.append(role)
    await session.commit()
    actor = await _seed_admin(session, "actor", [["admins:manage"]])
    invalidated: list[int] = []

    async def fake_invalidate(admin_id: int) -> None:
        invalidated.append(admin_id)

    monkeypatch.setattr(admins_service, "invalidate_admin_permissions", fake_invalidate)
    await admins_service.delete_admin(session, target, actor.id)

    assert invalidated == [target.id]
    assert (
        await session.execute(select(Admin).where(Admin.id == target.id))
    ).scalar_one_or_none() is None
    # the role survives; the admin_roles link is gone
    assert (await session.execute(select(Role).where(Role.id == role.id))).scalar_one() is not None
    remaining = (
        (
            await session.execute(
                select(admin_roles.c.admin_id).where(admin_roles.c.role_id == role.id)
            )
        )
        .scalars()
        .all()
    )
    assert list(remaining) == []
    # audit trail
    entries = (await session.execute(select(AuditLog))).scalars().all()
    assert any(e.action == "delete" and e.resource == "admins" for e in entries)


async def test_delete_admin_cannot_delete_self(session):
    admin = await _seed_admin(session, "bob", [["admins:manage"]])
    with pytest.raises(BadRequestError):
        await admins_service.delete_admin(session, admin, admin.id)


# ---------------------------------------------------------------------------
# delete_role
# ---------------------------------------------------------------------------


async def test_delete_role_unassigns_members_and_invalidates(session, monkeypatch):
    role = await _seed_role(session, "support", ["subscribers:read"])
    member1 = await _reload_with_roles(session, (await _seed_admin(session, "m1")).id)
    member2 = await _reload_with_roles(session, (await _seed_admin(session, "m2")).id)
    member1.roles.append(role)
    member2.roles.append(role)
    await session.commit()
    actor = await _seed_admin(session, "actor", [["roles:manage"]])
    invalidated: list[int] = []

    async def fake_invalidate(admin_id: int) -> None:
        invalidated.append(admin_id)

    monkeypatch.setattr(admins_service, "invalidate_admin_permissions", fake_invalidate)
    await admins_service.delete_role(session, role, actor.id)

    assert sorted(invalidated) == sorted([member1.id, member2.id])
    assert (
        await session.execute(select(Role).where(Role.id == role.id))
    ).scalar_one_or_none() is None
    # members survive, unassigned (association rows gone)
    remaining = (
        (
            await session.execute(
                select(admin_roles.c.admin_id).where(admin_roles.c.role_id == role.id)
            )
        )
        .scalars()
        .all()
    )
    assert list(remaining) == []
    for member in (member1, member2):
        assert (
            await session.execute(select(Admin).where(Admin.id == member.id))
        ).scalar_one() is not None


async def test_delete_role_self_manage_guard(session):
    # the actor's only role grants *:*; deleting it would lock them out
    actor = await _seed_admin(session, "actor", [["*:*"]])
    with pytest.raises(BadRequestError):
        await admins_service.delete_role(session, actor.roles[0], actor.id)


async def test_delete_role_allowed_when_manage_kept_elsewhere(session):
    actor = await _seed_admin(session, "actor", [["*:*"], ["admins:manage"]])
    role = actor.roles[0]  # the *:* role
    await admins_service.delete_role(session, role, actor.id)
    assert (
        await session.execute(select(Role).where(Role.id == role.id))
    ).scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------


async def test_get_admin_or_404(session):
    admin = await _seed_admin(session, "bob")
    found = await admins_service.get_admin_or_404(session, admin.id)
    assert found.id == admin.id
    with pytest.raises(NotFoundError):
        await admins_service.get_admin_or_404(session, 999)


async def test_list_admins_paginates(session):
    for i in range(3):
        await _seed_admin(session, f"u{i}")
    page1, total = await admins_service.list_admins(session, page=1, page_size=2)
    assert len(page1) == 2
    assert total == 3
    page2, _ = await admins_service.list_admins(session, page=2, page_size=2)
    assert len(page2) == 1
