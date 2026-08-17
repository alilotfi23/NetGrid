"""Pure RBAC logic: permission matching and permission-set versioning.

No app imports on purpose — this module must stay import-free of the rest of
the codebase so `app/services/rbac.py` and `app/api/deps.py` can both use it
without cycles. The FastAPI `require_permission` dependency lives in
`app/api/deps.py`.
"""

import hashlib
from collections.abc import Iterable

# Upper bound on how long a permission change can stay invisible (CLAUDE.md:
# "never let a revoked permission stay valid longer than a short cache TTL").
PERM_CACHE_TTL_SECONDS = 60


def permission_matches(granted: str, required: str) -> bool:
    """Exact or wildcard match. `*` in either `resource` or `action` matches any value."""
    if granted == required:
        return True
    granted_resource, _, granted_action = granted.partition(":")
    required_resource, _, required_action = required.partition(":")
    if granted_resource == "*" and (granted_action == "*" or granted_action == required_action):
        return True
    if granted_action == "*" and (granted_resource == "*" or granted_resource == required_resource):
        return True
    return False


def has_permission(granted_codes: Iterable[str], required: str) -> bool:
    return any(permission_matches(code, required) for code in granted_codes)


def version_of(codes: Iterable[str]) -> str:
    """Deterministic fingerprint of a permission set — changes iff the set changes."""
    joined = "|".join(sorted(codes))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]
