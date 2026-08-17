import pytest

from app.core.rbac import (
    PERM_CACHE_TTL_SECONDS,
    has_permission,
    permission_matches,
    version_of,
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
