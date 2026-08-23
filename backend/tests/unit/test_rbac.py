import os

import pytest

from app.core.rbac import (
    PERM_CACHE_TTL_SECONDS,
    has_permission,
    permission_matches,
    version_of,
)
from app.core.security import hash_password
from app.models.rbac import Admin, Permission, Role
from app.services import rbac as rbac_service
from app.services.rbac import (
    get_permission_state,
    invalidate_admin_permissions,
    resolve_admin_permissions,
)


@pytest.mark.parametrize(
    ("granted", "required", "expected"),
    [
        ("subscribers:read", "subscribers:read", True),  # exact
        ("subscribers:read", "subscribers:write", False),
        ("*:read", "subscribers:read", True),  # auditor wildcard
        ("*:read", "subscribers:write", False),
        ("*:read", "admins:read", True),
        ("subscribers:*", "subscribers:delete", True),  # any action on resource
        ("subscribers:*", "plans:read", False),
        ("*:*", "nas_devices:disconnect", True),  # super admin
        ("", "subscribers:read", False),
        ("admins:manage", "admins:manage", True),
    ],
)
def test_permission_matches(granted, required, expected):
    assert permission_matches(granted, required) is expected


def test_has_permission_any_match():
    assert has_permission(["plans:read", "subscribers:write"], "subscribers:write")
    assert has_permission(["*:read"], "invoices:read")
    assert not has_permission(["plans:read"], "subscribers:write")
    assert not has_permission([], "subscribers:read")


def test_version_is_deterministic_and_order_independent():
    assert version_of(["a:1", "b:2"]) == version_of(["b:2", "a:1"])


def test_version_changes_with_set():
    assert version_of(["a:1", "b:2"]) != version_of(["a:1"])


def test_ttl_is_at_most_60_seconds():
    assert 0 < PERM_CACHE_TTL_SECONDS <= 60


def test_cache_prefix_is_worker_scoped() -> None:
    """The permission-cache prefix (and its per-test clear) is worker-scoped.

    Under pytest-xdist the workers share one Redis but run separate databases
    where admin ids restart at 1, so a global namespace would let one worker's
    per-test clear wipe (or a stale read hit) another worker's live cache.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    assert rbac_service.CACHE_PREFIX == (f"rbac:perms:{worker}:" if worker else "rbac:perms:")


async def _seed_admin_with_roles(session, username="alice", role_codes=None) -> Admin:
    role_codes = role_codes or [
        ["plans:read"],
        ["subscribers:read", "subscribers:write"],
    ]
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    for codes in role_codes:
        role = Role(name=f"{username}_role_{len(admin.roles)}")
        role.permissions = [Permission(code=code) for code in codes]
        admin.roles.append(role)
    session.add(admin)
    await session.commit()
    return admin


async def test_resolve_admin_permissions_unions_roles(session):
    admin = await _seed_admin_with_roles(session)
    codes = await resolve_admin_permissions(session, admin.id)
    assert codes == {"plans:read", "subscribers:read", "subscribers:write"}


async def test_resolve_admin_permissions_empty_without_roles(session):
    admin = Admin(
        username="nobody", email="nobody@netgrid.local", password_hash="x", is_active=True
    )
    session.add(admin)
    await session.commit()
    assert await resolve_admin_permissions(session, admin.id) == set()


async def test_get_permission_state_caches(session, monkeypatch):
    admin = await _seed_admin_with_roles(session)
    calls = {"n": 0}
    original_resolve = rbac_service.resolve_admin_permissions

    async def counting_resolve(session, admin_id):
        calls["n"] += 1
        return await original_resolve(session, admin_id)

    monkeypatch.setattr(rbac_service, "resolve_admin_permissions", counting_resolve)
    first = await get_permission_state(session, admin.id)
    second = await get_permission_state(session, admin.id)
    assert calls["n"] == 1  # second call served from cache
    assert first == second
    assert first.version == version_of(first.codes)


async def test_invalidate_admin_permissions_refetches(session, monkeypatch):
    admin = await _seed_admin_with_roles(session)
    calls = {"n": 0}
    original_resolve = rbac_service.resolve_admin_permissions

    async def counting_resolve(session, admin_id):
        calls["n"] += 1
        return await original_resolve(session, admin_id)

    monkeypatch.setattr(rbac_service, "resolve_admin_permissions", counting_resolve)
    await get_permission_state(session, admin.id)
    await invalidate_admin_permissions(admin.id)
    await get_permission_state(session, admin.id)
    assert calls["n"] == 2
