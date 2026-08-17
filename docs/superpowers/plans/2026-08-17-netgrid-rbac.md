# NetGrid RBAC Implementation Plan (Plan 3 of 5 — Day 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Role-based access control for admin users: a `require_permission("resource:action")` FastAPI dependency applied to every endpoint, `perm_version` claims in access tokens so permission changes invalidate tokens quickly, a Redis-cached effective-permission set with a ≤60s revocation TTL, and seeded `super_admin` (all permissions) + `auditor` (`*:read`) roles. From this phase forward, no endpoint ships without an explicit permission check (CLAUDE.md). Prerequisites: Plans 1–2 committed (Phases 0, 1, 2, 4 checked off; `get_current_admin`, JWT `perm_version`-ready `security.py`, seeded `super_admin` migration `5e84f4d13f0c`).

**Architecture:** Pure permission logic (`permission_matches`, `has_permission`, `version_of`, cache TTL) lives in `app/core/rbac.py` with **no app imports** (no cycles). DB resolution + the Redis cache live in `app/services/rbac.py`. The FastAPI dependency `require_permission(permission)` lives in `app/api/deps.py` next to `get_current_admin` (centralized, not inlined per-router — the CLAUDE.md requirement is that RBAC is its own module, not scattered; `core/rbac.py` holds the logic, `api/deps.py` the dependency). Access tokens gain a `perm_version` claim (a deterministic fingerprint of the admin's effective permission set, computed at login/refresh). At request time, `require_permission` resolves the admin's current permission state from a Redis cache (`rbac:perms:<admin_id>`, TTL 60s, DB on miss) and: (1) rejects the token with 401 if its `perm_version` no longer matches (permissions changed → re-login), (2) returns 403 if the permission is missing. Role/permission changes call `invalidate_admin_permissions(admin_id)` (best-effort delete; the 60s TTL self-heals even without it). Wildcards: `*:read` matches any `resource:read` (auditor), `*:*` matches everything (super_admin), `resource:*` matches any action on a resource.

**Tech Stack:** no new dependencies. Uses existing: passlib/PyJWT (Plan 2), redis.asyncio (`app/core/redis.py`), SQLAlchemy async, slowapi. Postgres + Redis containers must be running for every task.

## Global Constraints

- Same as Plans 1–2: `/api/v1` + error envelope; routers thin → services own DB access; services never import from `api/`; real Postgres for tests; ruff + `mypy --strict` clean before each commit; Conventional Commits; commit per task.
- **Layering rule for RBAC:** `app/core/rbac.py` must not import from `app/` (pure logic only). `app/services/rbac.py` may import from `app/core` and `app/models`. `require_permission` lives in `app/api/deps.py` (it is a FastAPI dependency; putting it in `core/` would create a `core → services` cycle).
- **Breaking change:** `get_current_admin` now returns `CurrentAdmin(admin, payload)` (a frozen dataclass in `app/api/deps.py`) instead of `Admin`, so dependencies can read token claims. `GET /auth/me` switches to `require_permission("admins:read")`. Update the Plan 2 auth tests accordingly (seeded test admins need a role granting `admins:read`, or `/me` returns 403).
- **Cache semantics:** the permission cache is best-effort — a Redis outage must not break auth (fall back to DB resolution, skip caching). `perm_version` mismatch returns 401 ("Permissions changed, please sign in again"), a missing permission returns 403. Auth endpoints (`login`/`refresh`/`logout`) remain permission-exempt but `login`/`refresh` embed the current `perm_version` into access tokens.
- `perm_version` is a **deterministic fingerprint** (sha256 of the sorted permission codes, truncated to 16 hex chars) — no DB column or bump logic needed; it changes iff the set changes.
- Do not build admin/role management endpoints in this plan (that is a later phase). Provide `invalidate_admin_permissions` as the service function future endpoints will call, and prove it works in tests.

## File Structure

```
/backend
  app/
    core/
      rbac.py               # NEW pure logic: permission_matches, has_permission, version_of, PERM_CACHE_TTL_SECONDS
      security.py           # MODIFIED: access tokens accept/embed perm_version claim
    services/
      rbac.py               # NEW: resolve_admin_permissions, PermissionState, get_permission_state, invalidate_admin_permissions
      auth.py               # MODIFIED: build_token_pair async, embeds perm_version (imports services.rbac)
    api/
      deps.py               # MODIFIED: CurrentAdmin dataclass, get_current_admin returns it, NEW require_permission
      v1/
        auth.py             # MODIFIED: /me uses require_permission("admins:read"); login awaits build_token_pair
    models/                 # unchanged — roles/permissions/admin_roles/role_permissions already exist
  alembic/versions/<hash>_add_auditor_and_wildcard_permissions.py   # NEW data migration
  tests/
    unit/
      test_rbac.py          # NEW: matcher, version_of, permission resolution, cache behavior
    integration/
      test_rbac.py          # NEW: allowed/denied per role, wildcard, revocation (stale token + re-login)
      test_auth.py          # MODIFIED: /me tests seed a role with admins:read
  schemas/                  # unchanged
```

---

### Task 1: Pure RBAC logic + `perm_version` JWT claim

**Files:**
- Create: `backend/app/core/rbac.py`
- Modify: `backend/app/core/security.py` (`_encode` + `create_access_token` accept `perm_version`)
- Test: `backend/tests/unit/test_rbac.py` (matcher + version), extend `backend/tests/unit/test_security.py`

**Interfaces:**
- `app.core.rbac.permission_matches(granted: str, required: str) -> bool` — exact match, or wildcard match: `*` in either `resource` or `action` segment of the granted code matches any value (`*:read` matches `subscribers:read`; `subscribers:*` matches `subscribers:write`; `*:*` matches everything).
- `app.core.rbac.has_permission(granted_codes: Iterable[str], required: str) -> bool` — true if any granted code matches.
- `app.core.rbac.version_of(codes: Iterable[str]) -> str` — sha256 of `"|".join(sorted(codes))`, truncated to 16 hex chars.
- `app.core.rbac.PERM_CACHE_TTL_SECONDS = 60` — the revocation bound.
- `app.core.security.create_access_token(subject: str, perm_version: str | None = None) -> str` — embeds `perm_version` claim when provided.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_rbac.py`:

```python
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
```

Extend `backend/tests/unit/test_security.py` with:

```python
def test_access_token_embeds_perm_version():
    token = security.create_access_token("7", perm_version="abc123")
    payload = security.decode_token(token, expected_type="access")
    assert payload["perm_version"] == "abc123"


def test_access_token_without_perm_version():
    token = security.create_access_token("7")
    payload = security.decode_token(token, expected_type="access")
    assert "perm_version" not in payload
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
source .venv/Scripts/activate
pytest tests/unit/test_rbac.py tests/unit/test_security.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.rbac'`.

- [ ] **Step 3: Implement**

Create `backend/app/core/rbac.py`:

```python
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
```

Modify `backend/app/core/security.py`:

```python
def _encode(
    subject: str, token_type: str, ttl: timedelta, perm_version: str | None = None
) -> tuple[str, str]:
    """Encode a JWT; returns (token, jti) so logout/rotation can revoke it."""
    settings = get_settings()
    jti = uuid4().hex
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }
    if perm_version is not None:
        payload["perm_version"] = perm_version
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, jti


def create_access_token(subject: str, perm_version: str | None = None) -> str:
    ttl = timedelta(minutes=get_settings().jwt_access_ttl_minutes)
    token, _ = _encode(subject, TOKEN_TYPE_ACCESS, ttl, perm_version=perm_version)
    return token
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_rbac.py tests/unit/test_security.py -v
```

Expected: PASS (10 parametrized matcher cases + 2 has_permission + 3 version + 1 ttl + 11 security).

> Note for the executing agent: pytest reports the actual count; the requirement is that every new/extended test passes.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/core/rbac.py app/core/security.py tests/unit/test_rbac.py tests/unit/test_security.py
git commit -m "feat: add RBAC permission matching and perm_version JWT claim"
```

---

### Task 2: Effective-permission resolution with 60s Redis cache

**Files:**
- Create: `backend/app/services/rbac.py`
- Modify: `backend/app/services/auth.py` (`build_token_pair` becomes async, embeds `perm_version`)
- Test: extend `backend/tests/unit/test_rbac.py`

**Interfaces:**
- `app.services.rbac.PermissionState` — frozen dataclass `{version: str, codes: frozenset[str]}`.
- `resolve_admin_permissions(session, admin_id) -> set[str]` — union of permission codes across the admin's roles (DB; eager-loads roles→permissions).
- `get_permission_state(session, admin_id) -> PermissionState` — Redis cache `rbac:perms:<admin_id>` (JSON `{version, codes}`, TTL 60s); on miss or cache outage, resolves from DB and (best-effort) writes the cache.
- `invalidate_admin_permissions(admin_id) -> None` — deletes the cache key (best-effort; the TTL self-heals otherwise).
- `app.services.auth.build_token_pair(session, admin) -> dict[str, str]` — **now async**: resolves the permission state and embeds `perm_version` into the access token. `refresh_tokens` uses it unchanged.

- [ ] **Step 1: Write the failing tests**

Extend `backend/tests/unit/test_rbac.py`:

```python
from unittest.mock import AsyncMock

from app.core.rbac import version_of
from app.core.security import hash_password
from app.models.rbac import Admin, Permission, Role
from app.services import rbac as rbac_service
from app.services.rbac import get_permission_state, invalidate_admin_permissions, resolve_admin_permissions


async def _seed_admin_with_roles(session, username="alice", role_codes=None) -> Admin:
    role_codes = role_codes or [["plans:read"], ["subscribers:read", "subscribers:write"]]
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
    admin = Admin(username="nobody", email="nobody@netgrid.local", password_hash="x", is_active=True)
    session.add(admin)
    await session.commit()
    assert await resolve_admin_permissions(session, admin.id) == set()


async def test_get_permission_state_caches(session, monkeypatch):
    admin = await _seed_admin_with_roles(session)
    calls = {"n": 0}

    async def counting_resolve(session, admin_id):
        calls["n"] += 1
        return await rbac_service.resolve_admin_permissions(session, admin_id)

    monkeypatch.setattr(rbac_service, "resolve_admin_permissions", counting_resolve)
    first = await get_permission_state(session, admin.id)
    second = await get_permission_state(session, admin.id)
    assert calls["n"] == 1  # second call served from cache
    assert first == second
    assert first.version == version_of(first.codes)


async def test_invalidate_admin_permissions_refetches(session, monkeypatch):
    admin = await _seed_admin_with_roles(session)
    calls = {"n": 0}

    async def counting_resolve(session, admin_id):
        calls["n"] += 1
        return await rbac_service.resolve_admin_permissions(session, admin_id)

    monkeypatch.setattr(rbac_service, "resolve_admin_permissions", counting_resolve)
    await get_permission_state(session, admin.id)
    await invalidate_admin_permissions(admin.id)
    await get_permission_state(session, admin.id)
    assert calls["n"] == 2
```

> These tests use real Redis (like the Plan 2 blacklist tests); Redis must be running.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/unit/test_rbac.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.rbac'`.

- [ ] **Step 3: Implement**

Create `backend/app/services/rbac.py`:

```python
"""Effective-permission resolution for admins, with a short-TTL Redis cache.

The cache is best-effort: a Redis outage falls back to DB resolution and
skips caching, so RBAC never breaks auth.
"""
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rbac import PERM_CACHE_TTL_SECONDS, version_of
from app.core.redis import get_redis
from app.models.rbac import Admin, Permission, Role

CACHE_KEY = "rbac:perms:{}"


@dataclass(frozen=True)
class PermissionState:
    version: str
    codes: frozenset[str]


async def resolve_admin_permissions(session: AsyncSession, admin_id: int) -> set[str]:
    """Union of permission codes across the admin's roles."""
    admin = await session.get(
        Admin, admin_id, options=[selectinload(Admin.roles).selectinload(Role.permissions)]
    )
    if admin is None:
        return set()
    return {permission.code for role in admin.roles for permission in role.permissions}


async def _read_cache(admin_id: int) -> PermissionState | None:
    redis = get_redis()
    try:
        raw = await redis.get(CACHE_KEY.format(admin_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return PermissionState(data["version"], frozenset(data["codes"]))
    except Exception:
        return None  # cache outage -> slow path
    finally:
        await redis.aclose()


async def _write_cache(admin_id: int, state: PermissionState) -> None:
    redis = get_redis()
    try:
        await redis.set(
            CACHE_KEY.format(admin_id),
            json.dumps({"version": state.version, "codes": sorted(state.codes)}),
            ex=PERM_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass  # best-effort
    finally:
        await redis.aclose()


async def get_permission_state(session: AsyncSession, admin_id: int) -> PermissionState:
    cached = await _read_cache(admin_id)
    if cached is not None:
        return cached
    codes = await resolve_admin_permissions(session, admin_id)
    state = PermissionState(version_of(codes), frozenset(codes))
    await _write_cache(admin_id, state)
    return state


async def invalidate_admin_permissions(admin_id: int) -> None:
    """Drop the cached permission set (call after any role/permission change)."""
    redis = get_redis()
    try:
        await redis.delete(CACHE_KEY.format(admin_id))
    except Exception:
        pass  # TTL self-heals
    finally:
        await redis.aclose()
```

> `select`/`Permission` are imported for typing clarity in the eager-load query (`session.get` uses `selectinload`); if ruff flags unused imports, drop them.

Modify `backend/app/services/auth.py`:

```python
from app.services.rbac import get_permission_state

async def build_token_pair(session: AsyncSession, admin: Admin) -> dict[str, str]:
    state = await get_permission_state(session, admin.id)
    access = create_access_token(str(admin.id), perm_version=state.version)
    refresh, _ = create_refresh_token(str(admin.id))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}
```

And `refresh_tokens` ends with `return await build_token_pair(session, admin)` (was `return build_token_pair(admin)`).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_rbac.py tests/unit/test_auth_service.py -q
```

Expected: PASS — the new cache tests and the existing service tests (refresh now resolves permissions; role-less seeded admins yield the empty-set version, so nothing breaks).

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/services/rbac.py app/services/auth.py tests/unit/test_rbac.py
git commit -m "feat: add cached effective-permission resolution with 60s revocation TTL"
```

---

### Task 3: Seed `auditor` role + wildcard permissions (migration)

**Files:**
- Create: `backend/alembic/versions/<hash>_add_auditor_and_wildcard_permissions.py` (via `alembic revision -m "add auditor and wildcard permissions"`; down_revision = `5e84f4d13f0c`)

**Interfaces:**
- Upgrade adds permissions `*:read` and `*:*`; creates role `auditor` (description "Read-only access to all resources") linked to `*:read`; links `*:*` to the existing `super_admin` role.
- Downgrade removes the auditor role, the two wildcard permission rows, and the `super_admin`↔`*:*` link (FK-safe order). Same caveat as the Plan-2 seed migration: downgrade deletes the seeded wildcard permissions outright.

- [ ] **Step 1: Generate the migration stub**

```bash
cd backend
source .venv/Scripts/activate
alembic revision -m "add auditor and wildcard permissions"
```

- [ ] **Step 2: Implement** (fill the generated file; same `sa.table` pattern as `5e84f4d13f0c`)

```python
"""add auditor and wildcard permissions

Revision ID: <generated>
Revises: 5e84f4d13f0c
Create Date: <generated>

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "<generated>"
down_revision: Union[str, Sequence[str], None] = "5e84f4d13f0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUDITOR_ROLE = "auditor"
AUDITOR_ROLE_DESC = "Read-only access to all NetGrid resources"
WILDCARD_READ = "*:read"
WILDCARD_ALL = "*:*"
SUPERADMIN_ROLE = "super_admin"

roles = sa.table(
    "roles",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
)
permissions = sa.table(
    "permissions",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
)
role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("permission_id", sa.Integer),
)


def _get_or_create_id(conn, table, id_col, match_col, value, **insert_values) -> int:
    existing = conn.execute(sa.select(id_col).where(match_col == value)).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    return int(conn.execute(sa.insert(table).values(**insert_values).returning(id_col)).scalar_one())


def _link(conn, role_id: int, permission_id: int) -> None:
    conn.execute(
        pg_insert(role_permissions)
        .values(role_id=role_id, permission_id=permission_id)
        .on_conflict_do_nothing()
    )


def upgrade() -> None:
    """Seed the auditor role and wildcard permissions; make super_admin use *:*."""
    conn = op.get_bind()

    read_id = _get_or_create_id(
        conn, permissions, permissions.c.id, permissions.c.code, WILDCARD_READ, code=WILDCARD_READ
    )
    all_id = _get_or_create_id(
        conn, permissions, permissions.c.id, permissions.c.code, WILDCARD_ALL, code=WILDCARD_ALL
    )

    auditor_id = _get_or_create_id(
        conn, roles, roles.c.id, roles.c.name, AUDITOR_ROLE,
        name=AUDITOR_ROLE, description=AUDITOR_ROLE_DESC,
    )
    _link(conn, auditor_id, read_id)

    super_admin_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == SUPERADMIN_ROLE)
    ).scalar_one_or_none()
    if super_admin_id is not None:
        _link(conn, int(super_admin_id), all_id)


def downgrade() -> None:
    """Remove the auditor role, wildcard permissions, and super_admin's *:* link."""
    conn = op.get_bind()

    auditor_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == AUDITOR_ROLE)
    ).scalar_one_or_none()
    if auditor_id is not None:
        conn.execute(
            sa.delete(role_permissions).where(role_permissions.c.role_id == auditor_id)
        )
        conn.execute(sa.delete(roles).where(roles.c.id == auditor_id))

    for code in (WILDCARD_READ, WILDCARD_ALL):
        perm_id = conn.execute(
            sa.select(permissions.c.id).where(permissions.c.code == code)
        ).scalar_one_or_none()
        if perm_id is not None:
            conn.execute(
                sa.delete(role_permissions).where(role_permissions.c.permission_id == perm_id)
            )
            conn.execute(sa.delete(permissions).where(permissions.c.id == perm_id))
```

- [ ] **Step 3: Verify upgrade/downgrade/upgrade against the dev DB**

```bash
alembic upgrade head
docker compose exec -T postgres psql -U netgrid -d netgrid -c \
  "SELECT r.name AS role, count(rp.permission_id) AS perms FROM roles r JOIN role_permissions rp ON rp.role_id = r.id GROUP BY r.name ORDER BY r.name;"
alembic downgrade -1
alembic upgrade head
```

Expected: `auditor` with 1 permission, `super_admin` with 13 (12 literal + `*:*`); downgrade removes them; re-upgrade restores.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions
git commit -m "feat: seed auditor role and wildcard permissions"
```

---

### Task 4: `require_permission` + gate `/auth/me` + integration coverage

**Files:**
- Modify: `backend/app/api/deps.py` (CurrentAdmin, `get_current_admin` returns it, `require_permission`), `backend/app/api/v1/auth.py` (`/me` gated; `login` awaits `build_token_pair`)
- Test: create `backend/tests/integration/test_rbac.py`; modify `backend/tests/integration/test_auth.py` (seed roles for `/me` tests)

**Interfaces:**
- `app.api.deps.CurrentAdmin` — frozen dataclass `{admin: Admin, payload: dict[str, Any]}` (decoded access-token claims).
- `get_current_admin(...) -> CurrentAdmin` — same logic as before (bearer → decode → load admin + active check), now also returns the payload so dependencies can read `perm_version`.
- `app.api.deps.require_permission(permission: str)` — dependency factory; depends on `get_current_admin` + session; resolves `PermissionState`; raises `UnauthorizedError` (401) on `perm_version` mismatch, `ForbiddenError` (403) when the permission is missing; returns the `Admin`.
- `GET /api/v1/auth/me` — now `Depends(require_permission("admins:read"))` (still rate-limited 60/min).
- `POST /api/v1/auth/login` — `pair = await auth_service.build_token_pair(session, admin)`.

- [ ] **Step 1: Update `app/api/deps.py`**

```python
"""Shared FastAPI dependencies for authenticated endpoints."""
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.rbac import has_permission
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.models.rbac import Admin
from app.services.auth import get_admin_by_id
from app.services.rbac import get_permission_state

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentAdmin:
    admin: Admin
    payload: dict[str, Any]  # decoded access-token claims (sub, type, jti, perm_version, ...)


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentAdmin:
    """Resolve the authenticated admin + token claims.

    Authentication only — authorization goes through require_permission(...).
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_token(credentials.credentials, expected_type=TOKEN_TYPE_ACCESS)
    admin = await get_admin_by_id(session, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise UnauthorizedError("Admin no longer active")
    return CurrentAdmin(admin=admin, payload=payload)


def require_permission(permission: str):
    """Dependency factory: authentication + permission check.

    Rejects a token whose perm_version no longer matches the admin's current
    permission set (401, forces re-login after any role change) and returns
    403 when the permission is missing.
    """

    async def dependency(
        current: Annotated[CurrentAdmin, Depends(get_current_admin)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> Admin:
        state = await get_permission_state(session, current.admin.id)
        if state.version != current.payload.get("perm_version"):
            raise UnauthorizedError("Permissions changed, please sign in again")
        if not has_permission(state.codes, permission):
            raise ForbiddenError()
        return current.admin

    return dependency
```

- [ ] **Step 2: Update `app/api/v1/auth.py`**

`login`:

```python
@router.post("/login", response_model=LoginResponse)
@limiter.limit(LIMITS["login"])
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: SessionDep,
) -> LoginResponse:
    """POST /api/v1/auth/login — no permission required (auth endpoint)."""
    admin = await auth_service.authenticate_admin(session, payload.username, payload.password)
    pair = await auth_service.build_token_pair(session, admin)
    return LoginResponse(admin=AdminOut.model_validate(admin), **pair)
```

`me`:

```python
@router.get("/me", response_model=AdminOut)
@limiter.limit(LIMITS["me"])
async def me(
    request: Request,
    response: Response,
    admin: Annotated[Admin, Depends(require_permission("admins:read"))],
) -> AdminOut:
    """GET /api/v1/auth/me — requires the admins:read permission (via require_permission)."""
    return AdminOut.model_validate(admin)
```

Update the import: `from app.api.deps import require_permission` (drop `get_current_admin`).

- [ ] **Step 3: Write the failing integration tests**

Create `backend/tests/integration/test_rbac.py`:

```python
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import hash_password
from app.models.rbac import Admin, Permission, Role
from app.services.rbac import invalidate_admin_permissions


async def _seed_admin_with_permissions(session, codes, username="boss") -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password("secret123"),
        is_active=True,
    )
    role = Role(name=f"role_{username}")
    role.permissions = [Permission(code=code) for code in codes]
    admin.roles.append(role)
    session.add(admin)
    await session.commit()
    return admin


async def _login(client, username="boss", password="secret123"):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def test_me_allowed_with_permission(client, session):
    await _seed_admin_with_permissions(session, ["admins:read", "plans:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "boss"


async def test_me_denied_without_permission(client, session):
    await _seed_admin_with_permissions(session, ["plans:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_me_auditor_wildcard_read(client, session):
    # auditor-style role: *:read matches admins:read via the wildcard
    await _seed_admin_with_permissions(session, ["*:read"])
    token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


async def test_revocation_rejects_stale_token(client, session):
    await _seed_admin_with_permissions(session, ["admins:read"])
    token = await _login(client)
    # revoke: strip the role's permissions and drop the cache
    admin = (
        await session.execute(select(Admin).where(Admin.username == "boss"))
    ).scalar_one()
    admin.roles[0].permissions.clear()
    await session.commit()
    await invalidate_admin_permissions(admin.id)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_revocation_denies_after_relogin(client, session):
    await _seed_admin_with_permissions(session, ["admins:read"])
    await _login(client)  # burn the pre-revocation token so its version is stale
    admin = (
        await session.execute(select(Admin).where(Admin.username == "boss"))
    ).scalar_one()
    admin.roles[0].permissions.clear()
    await session.commit()
    await invalidate_admin_permissions(admin.id)
    # a fresh login gets a token with the new perm_version — then the check is a 403
    new_token = await _login(client)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
```

Update `backend/tests/integration/test_auth.py`: the `_seed_admin` helper must grant `admins:read` so the existing `test_me_with_token` keeps passing:

```python
async def _seed_admin(session, username="root", password="secret123") -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password(password),
        is_active=True,
    )
    role = Role(name=f"role_{username}")
    role.permissions = [Permission(code="admins:read")]
    admin.roles.append(role)
    session.add(admin)
    await session.commit()
    return admin
```

(imports: `from app.models.rbac import Admin, Permission, Role`)

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/integration/test_rbac.py tests/integration/test_auth.py -v
```

Expected: PASS — 5 new RBAC tests + the 8 auth tests (with the updated seed). Requires Postgres + Redis running.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/api/deps.py app/api/v1/auth.py tests/integration/test_rbac.py tests/integration/test_auth.py
git commit -m "feat: enforce RBAC via require_permission on /auth/me"
```

---

### Task 5: Full gates + CLAUDE.md sync

**Files:**
- Modify: `CLAUDE.md` (check Phase 3, record implementation specifics)

- [ ] **Step 1: Run the full suite and every gate**

```bash
docker compose up -d postgres redis   # from repo root, if not already up
cd backend
source .venv/Scripts/activate
ruff check app tests
ruff format --check app tests
mypy app
pytest -q
```

Expected: ruff clean, mypy clean, full suite green (previous 40 tests, updated where needed, plus the new RBAC tests).

- [ ] **Step 2: Update `CLAUDE.md`**

Apply exactly these changes:

1. In `Build Phases`, check off **Phase 3 — RBAC**: change `- [ ]` to `- [x]`.
2. In the `RBAC > Enforcement` section, replace the first bullet with implementation specifics:

```
- Implement as a FastAPI dependency: `require_permission("subscribers:write")` in `app/api/deps.py` (pure matching logic in `app/core/rbac.py`), applied per-route — never enforce RBAC only in the frontend. Wildcards are supported: `*:read` matches any `resource:read`, `*:*` matches everything.
```

3. In `RBAC > Enforcement`, after the "permission-version or role hash in the JWT" bullet, append:

```
- Implementation: access tokens carry a `perm_version` claim (fingerprint of the admin's effective permission set, computed at login/refresh); the effective set is cached in Redis (`rbac:perms:<admin_id>`, 60s TTL, DB on miss, cache is best-effort); role/permission changes call `invalidate_admin_permissions(admin_id)`; a token whose `perm_version` no longer matches is rejected with 401 (re-login), a missing permission is 403.
```

4. In `RBAC > Model`, after the `admin_roles` bullet, add a note that the seed migration creates `super_admin` (all permissions incl. `*:*`) and `auditor` (`*:read`).

- [ ] **Step 3: Final commit**

```bash
cd ..
git add CLAUDE.md
git commit -m "docs: check off Phase 3, record RBAC implementation in CLAUDE.md"
```

---

## Self-Review (to verify when implementing)

- **Spec coverage:** every Phase 3 deliverable from CLAUDE.md maps to a task — `require_permission` (T4), perm-version claim / Redis cache / ≤60s TTL (T1, T2), seeded `super_admin` + `auditor` roles (T3), `/auth/me` gated so no endpoint ships without an explicit permission from this point on (T4), full unit + integration coverage: permission resolution + caching (T2), access denied/allowed per role + revocation (T4).
- **Placeholder scan:** no TBD/TODO; every code step carries full content. The `<hash>`/`<generated>` values in Task 3 are filled by `alembic revision`, exactly as in Plans 1–2.
- **Layering compliance:** `core/rbac.py` is pure (no app imports, no cycles); DB access lives in `services/rbac.py` + `services/auth.py`; the dependency lives in `api/deps.py`; routers stay thin.
- **Type consistency:** `CurrentAdmin(admin, payload)` is the single token-carrying type; `PermissionState(version, codes)` is the single permission-state type; `perm_version` claim name is used identically in security.py, services/auth.py, api/deps.py, and tests. `build_token_pair` becomes async — every caller is awaited (login, refresh_tokens).
- **Known ripple:** gating `/me` with `admins:read` makes the Plan 2 auth tests' seeded admins (no roles) get 403 — Task 4 updates the seed helper. Tests keep running against real Postgres + Redis (both provisioned by CI's backend job, no workflow changes needed).
- **Out of scope by design (later plans):** admin/role management CRUD endpoints (they will call `invalidate_admin_permissions`), permission-editing UI, applying `require_permission` to future resource routers (Phase 5+ must do so per policy).
