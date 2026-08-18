# NetGrid Subscribers Implementation Plan (Plan 5 of 5 — Day 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subscriber management for the NetGrid platform: a full CRUD API (`/api/v1/subscribers`) gated by `subscribers:read/write/delete`, with the profile row (`subscribers`) and the FreeRADIUS credential rows (`radcheck`) written in the **same transaction** (the CLAUDE.md direct-coupling decision). Credentials never touch the `subscribers` table — the password lives only in `radcheck` as a `Cleartext-Password` check item, and a subscriber whose status is not `active` gets an `Auth-Type := Reject` check so they cannot authenticate. Plan assignment (`radusergroup`) is deliberately deferred to Phase 6. Prerequisites: Plans 1–4 committed (Phases 0–4 checked off; `require_permission` + `get_current_admin` live; seeded `super_admin` with `subscribers:*` from migration `5e84f4d13f0c`; the `subscribers`/`plans` models exist from Phase 1).

**Architecture:** Subscriber auth is handled entirely by FreeRADIUS against `radcheck` (via its `sql` module, `authcheck_table = "radcheck"` — confirmed in the container config). The FastAPI service therefore mirrors the profile mutation into radcheck rows in the same session/transaction, then commits once. Concretely:
- **Create** → insert `subscribers` row + one `radcheck` row (`UserName`, `Attribute='Cleartext-Password'`, `op=':='`, `Value=<password>`); if `status != "active"`, also insert `Auth-Type := Reject`.
- **Password change** → upsert the `Cleartext-Password` row's `Value`.
- **Status change** → add/remove the `Auth-Type := Reject` row so only `active` subscribers authenticate.
- **Delete** → delete the `radcheck` rows for the username and the `subscribers` row in one transaction.

The `radcheck` table is **FreeRADIUS-owned** in dev/prod (created by the image's initdb, exact names from `freeradius/raddb/mods-config/sql/main/postgresql/schema.sql` — never rename) and is created in the test DB by `Base.metadata.create_all` once a `RadCheck` model is registered — so integration tests verify real rows without any fixture SQL. The hardened unique index `uq_radcheck_username_attribute` (indexes.sql) becomes a `UniqueConstraint` on the model so tests get the same DB-level enforcement. Duplicate usernames surface as `IntegrityError` → `409 CONFLICT` via the established `_commit_or_conflict` pattern. Usernames are **immutable** after creation (renaming would require rewriting radcheck rows — out of scope). `plan_id` exists on the model but is **not exposed** in Phase 5's API (setting it without writing `radusergroup` would create RADIUS-inconsistent state; Phase 6 adds `plan_id` + `radusergroup` writes together).

**Tech Stack:** no new dependencies. Uses existing: SQLAlchemy 2.0 async, FastAPI, slowapi (rate limits), `Page[T]` pagination, the error envelope, `app/services/audit.py`, and the `require_permission` dependency. Postgres + Redis containers must be running for every task; the `freeradius` container is needed only for Task 5's live `radtest` verification.

## Global Constraints

- Same as Plans 1–4: `/api/v1` routes; `{"error": {"code", "message"}}` envelope; routers thin (parse/validate → call services); all DB access lives in services; services never import from `api/`; real Postgres for tests (never SQLite); ruff + `mypy --strict` on `app/` clean before every commit; Conventional Commits; commit at the end of every task.
- **Direct coupling (CLAUDE.md):** the `radcheck` writes happen in the *same* transaction as the `subscribers` write, in the service layer — no sync job, no ETL, no RPC bridge. One commit per mutation.
- **Exact FreeRADIUS names:** `radcheck` columns are `UserName`, `Attribute`, `op`, `Value` — quoted in psql checks (`"UserName"`) because they are mixed-case. Do not rename or restructure (CLAUDE.md: "do not rename").
- **No Alembic migration:** `radcheck` already exists in dev/prod via the FreeRADIUS initdb; the test DB builds it from `Base.metadata.create_all`. The `subscribers:read/write/delete` permission codes are already seeded by `5e84f4d13f0c` (verified). This phase ships **zero migrations**.
- **RBAC gating:** every new endpoint declares its permission in its docstring and enforces it via `require_permission(...)` — no endpoint is reachable by "any authenticated admin".
- **Username immutability:** `SubscriberUpdate` has no `username` field; `SubscriberCreate.username` cannot be changed later.
- **Security note (deliberate):** radcheck stores the subscriber password as `Cleartext-Password` — FreeRADIUS needs a recoverable secret for PAP/MSCHAPv2 against NAS devices; this is the standard FreeRADIUS idiom and the credential never touches the `subscribers` table. Record this in CLAUDE.md in Task 5.

## File Structure

```
/backend
  app/
    models/
      radius.py               # NEW RadCheck — exact FreeRADIUS radcheck mapping
      __init__.py             # MODIFIED — register RadCheck (so tests' create_all builds radcheck)
    schemas/
      subscribers.py          # NEW SubscriberCreate / SubscriberUpdate / SubscriberOut
    services/
      subscribers.py          # NEW list/get/create/update/delete + radcheck sync helpers
    api/
      v1/
        subscribers.py        # NEW router — 5 endpoints, RBAC-gated, rate-limited
        router.py             # MODIFIED — include subscribers router
    core/
      rate_limit.py           # MODIFIED — subscriber_read / subscriber_write limits
  tests/
    unit/
      test_radius_model.py    # NEW — column defaults + unique(username, attribute)
      test_subscribers_service.py  # NEW — service layer incl. radcheck coupling
    integration/
      test_subscribers.py     # NEW — full CRUD via API, RBAC allow/deny, radcheck verification
  alembic/                    # NO migration (see Global Constraints)
```

---

### Task 1: `RadCheck` model + subscriber schemas + rate-limit tiers

**Files:**
- Create: `backend/app/models/radius.py`
- Modify: `backend/app/models/__init__.py` (register `RadCheck`)
- Create: `backend/app/schemas/subscribers.py`
- Modify: `backend/app/core/rate_limit.py` (two new limits)
- Test: `backend/tests/unit/test_radius_model.py`

**Interfaces:**
- `app.models.radius.RadCheck` — maps `radcheck` with exact FreeRADIUS column names: `id` (PK), `UserName` (Text, default `""`), `Attribute` (Text, default `""`), `op` (String(2), default `"=="`), `Value` (Text, default `""`); `UniqueConstraint("UserName", "Attribute", name="uq_radcheck_username_attribute")` mirroring `indexes.sql`.
- `app.schemas.subscribers.SubscriberCreate` — `username` (1–64, `^\S+$`), `full_name` (1–255), `email` (≤255, optional), `phone` (≤32, optional), `password` (8–128, required), `status` (`Literal["active","suspended","expired"]`, default `"active"`), `notes` (≤2000, optional). **No `plan_id`** — Phase 6.
- `app.schemas.subscribers.SubscriberUpdate` — all optional; **no `username`** (immutable); `status` validated against the same three values.
- `app.schemas.subscribers.SubscriberOut` — `from_attributes=True`; id, username, full_name, email, phone, status, `plan_id` (always `None` until Phase 6), notes, created_at.
- `app.core.rate_limit.LIMITS` — add `"subscriber_read": "60/minute"`, `"subscriber_write": "20/minute"` (same tiers as the admin endpoints).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_radius_model.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.radius import RadCheck


async def test_radcheck_defaults(session):
    row = RadCheck(UserName="u1", Attribute="Cleartext-Password", Value="pw")
    session.add(row)
    await session.commit()
    assert row.id is not None
    assert row.op == "=="  # FreeRADIUS default from schema.sql


async def test_radcheck_unique_username_attribute(session):
    session.add(RadCheck(UserName="u1", Attribute="Cleartext-Password", op=":=", Value="a"))
    await session.commit()
    session.add(RadCheck(UserName="u1", Attribute="Cleartext-Password", op=":=", Value="b"))
    with pytest.raises(IntegrityError):
        await session.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
source .venv/Scripts/activate
pytest tests/unit/test_radius_model.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.radius'`.

- [ ] **Step 3: Implement**

Create `backend/app/models/radius.py`:

```python
"""Read-write SQLAlchemy mapping of FreeRADIUS's radcheck table.

Exact table/column names from
freeradius/raddb/mods-config/sql/main/postgresql/schema.sql — do not rename
(CLAUDE.md). The app writes subscriber credentials here (direct coupling);
the table itself is created by the FreeRADIUS initdb in dev/prod and by
Base.metadata.create_all in tests. The UniqueConstraint mirrors the hardened
index uq_radcheck_username_attribute (indexes.sql).
"""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RadCheck(Base):
    __tablename__ = "radcheck"
    __table_args__ = (
        UniqueConstraint("UserName", "Attribute", name="uq_radcheck_username_attribute"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    UserName: Mapped[str] = mapped_column(Text, nullable=False, default="")
    Attribute: Mapped[str] = mapped_column(Text, nullable=False, default="")
    op: Mapped[str] = mapped_column(String(2), nullable=False, default="==")
    Value: Mapped[str] = mapped_column(Text, nullable=False, default="")
```

Modify `backend/app/models/__init__.py` — register the model so tests build the table:

```python
from .plan import Plan
from .radius import RadCheck
from .rbac import Admin, Permission, Role, admin_roles, role_permissions
```

and add `"RadCheck",` to `__all__`.

Create `backend/app/schemas/subscribers.py`:

```python
"""Pydantic schemas for subscriber management (Phase 5)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^\S+$"
SubscriberStatus = Literal["active", "suspended", "expired"]


class SubscriberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    status: str
    plan_id: int | None = None  # NULL until Phase 6 writes radusergroup
    notes: str | None = None
    created_at: datetime


class SubscriberCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    status: SubscriberStatus = "active"
    notes: str | None = Field(default=None, max_length=2000)


class SubscriberUpdate(BaseModel):
    # username is intentionally absent — immutable after creation
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    status: SubscriberStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
```

Modify `backend/app/core/rate_limit.py` — extend `LIMITS`:

```python
    "admin_read": "60/minute",
    "admin_write": "20/minute",
    # Phase 5 subscriber endpoints: reads loose, writes moderate.
    "subscriber_read": "60/minute",
    "subscriber_write": "20/minute",
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_radius_model.py -v
```

Expected: PASS — the test DB now contains `radcheck` (built from the model), defaults apply, and the duplicate `(username, attribute)` insert raises `IntegrityError`.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/models/radius.py app/models/__init__.py app/schemas/subscribers.py app/core/rate_limit.py tests/unit/test_radius_model.py
git commit -m "feat: add RadCheck model and subscriber schemas"
```

---

### Task 2: Subscriber service — queries + create (with radcheck coupling)

**Files:**
- Create: `backend/app/services/subscribers.py` (constants, `list_subscribers`, `get_subscriber_or_404`, `create_subscriber`, `_commit_or_conflict`, `_reject_check`)
- Test: `backend/tests/unit/test_subscribers_service.py`

**Interfaces:**
- `list_subscribers(session, page, page_size, q=None) -> tuple[list[Subscriber], int]` — paginated by id; `q` matches `username` or `full_name` case-insensitively.
- `get_subscriber_or_404(session, subscriber_id) -> Subscriber` — raises `NotFoundError` ("Subscriber not found").
- `create_subscriber(session, *, actor_id, username, full_name, password, email=None, phone=None, status="active", notes=None) -> Subscriber` — inserts the profile row + the `Cleartext-Password` radcheck row (+ `Auth-Type := Reject` when `status != "active"`) in one transaction; duplicate username → `ConflictError`; writes a `create`/`subscribers` audit entry.
- Constants: `RAD_PASSWORD_ATTRIBUTE = "Cleartext-Password"`, `RAD_AUTH_TYPE_ATTRIBUTE = "Auth-Type"`, `RAD_REJECT_VALUE = "Reject"`, `RAD_OP_SET = ":="`, `ACTIVE_STATUS = "active"`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_subscribers_service.py`:

```python
import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.radius import RadCheck
from app.models.rbac import Admin
from app.models.subscriber import Subscriber
from app.services import subscribers as subscribers_service

RAD_PASSWORD_ATTRIBUTE = subscribers_service.RAD_PASSWORD_ATTRIBUTE
RAD_AUTH_TYPE_ATTRIBUTE = subscribers_service.RAD_AUTH_TYPE_ATTRIBUTE


async def _radcheck_rows(session, username: str, attribute: str | None = None) -> list[RadCheck]:
    stmt = select(RadCheck).where(RadCheck.UserName == username)
    if attribute is not None:
        stmt = stmt.where(RadCheck.Attribute == attribute)
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
    assert rows[0].Attribute == RAD_PASSWORD_ATTRIBUTE
    assert rows[0].op == ":="
    assert rows[0].Value == "radpass123"


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
    assert {r.Attribute for r in rows} == {RAD_PASSWORD_ATTRIBUTE, RAD_AUTH_TYPE_ATTRIBUTE}
    reject = next(r for r in rows if r.Attribute == RAD_AUTH_TYPE_ATTRIBUTE)
    assert reject.Value == "Reject"


async def test_create_duplicate_username_conflict(session):
    actor = await _seed_actor(session)
    kwargs = dict(
        actor_id=actor.id, username="bob", full_name="Bob", password="radpass123"
    )
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
    filtered, total = await subscribers_service.list_subscribers(session, page=1, page_size=20, q="u1")
    assert [s.username for s in filtered] == ["u1"]
    assert total == 1


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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/unit/test_subscribers_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.subscribers'`.

- [ ] **Step 3: Implement**

Create `backend/app/services/subscribers.py`:

```python
"""Subscriber service: profile CRUD + direct RADIUS credential coupling.

Every mutation writes the `subscribers` row and the FreeRADIUS `radcheck`
rows it implies in a single transaction (CLAUDE.md direct-coupling decision):
the password lives only in radcheck as a `Cleartext-Password` check item, and
any status other than `active` adds an `Auth-Type := Reject` check so the
subscriber cannot authenticate. `plan_id` is deliberately not touched here —
plan assignment writes `radusergroup` and arrives with Phase 6.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.radius import RadCheck
from app.models.subscriber import Subscriber
from app.services import audit as audit_service

RAD_PASSWORD_ATTRIBUTE = "Cleartext-Password"
RAD_AUTH_TYPE_ATTRIBUTE = "Auth-Type"
RAD_REJECT_VALUE = "Reject"
RAD_OP_SET = ":="

ACTIVE_STATUS = "active"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def list_subscribers(
    session: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[Subscriber], int]:
    """Paginated subscriber list; `q` matches username or full name (case-insensitive)."""
    count_stmt = select(func.count()).select_from(Subscriber)
    stmt = select(Subscriber).order_by(Subscriber.id)
    if q:
        like = f"%{q}%"
        clause = or_(Subscriber.username.ilike(like), Subscriber.full_name.ilike(like))
        count_stmt = count_stmt.where(clause)
        stmt = stmt.where(clause)
    total = (await session.execute(count_stmt)).scalar_one()
    result = await session.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_subscriber_or_404(session: AsyncSession, subscriber_id: int) -> Subscriber:
    subscriber = (
        await session.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    ).scalar_one_or_none()
    if subscriber is None:
        raise NotFoundError("Subscriber not found")
    return subscriber


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_subscriber(
    session: AsyncSession,
    *,
    actor_id: int,
    username: str,
    full_name: str,
    password: str,
    email: str | None = None,
    phone: str | None = None,
    status: str = ACTIVE_STATUS,
    notes: str | None = None,
) -> Subscriber:
    """Create the profile row and its radcheck credential rows in one transaction."""
    subscriber = Subscriber(
        username=username,
        full_name=full_name,
        email=email,
        phone=phone,
        status=status,
        notes=notes,
    )
    session.add(subscriber)
    session.add(
        RadCheck(
            UserName=username,
            Attribute=RAD_PASSWORD_ATTRIBUTE,
            op=RAD_OP_SET,
            Value=password,
        )
    )
    if status != ACTIVE_STATUS:
        session.add(_reject_check(username))
    await _commit_or_conflict(session, "Username already exists")
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="create",
        resource="subscribers",
        resource_id=str(subscriber.id),
        metadata_={"username": username, "status": status},
    )
    return subscriber


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reject_check(username: str) -> RadCheck:
    return RadCheck(
        UserName=username,
        Attribute=RAD_AUTH_TYPE_ATTRIBUTE,
        op=RAD_OP_SET,
        Value=RAD_REJECT_VALUE,
    )


async def _commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, mapping unique-constraint violations to ConflictError."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise ConflictError(message) from None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_subscribers_service.py -v
```

Expected: PASS — 6 tests (profile + radcheck row written, suspended → Reject, duplicate → Conflict with rollback, 404, pagination + filter, audit entry).

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/services/subscribers.py tests/unit/test_subscribers_service.py
git commit -m "feat: add subscriber service with radcheck credential coupling (create/list)"
```

---

### Task 3: Subscriber service — update + delete (password upsert, status sync)

**Files:**
- Modify: `backend/app/services/subscribers.py` (`update_subscriber`, `delete_subscriber`, `_upsert_password`, `_set_reject`)
- Test: extend `backend/tests/unit/test_subscribers_service.py`

**Interfaces:**
- `update_subscriber(session, subscriber, *, actor_id, full_name=None, email=None, phone=None, password=None, status=None, notes=None) -> Subscriber` — applies only provided fields; `password` upserts the `Cleartext-Password` row; `status` adds/removes the `Auth-Type := Reject` row; commits once; `update`/`subscribers` audit entry with the changed-field list.
- `delete_subscriber(session, subscriber, actor_id) -> None` — deletes every radcheck row for the username + the profile row in one transaction; `delete`/`subscribers` audit entry.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_subscribers_service.py`:

```python
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
    assert rows[0].Value == "newpass456"


async def test_update_status_syncs_reject(session):
    subscriber = await _create(session)  # active -> no reject row
    actor = await _seed_actor(session, "actor2")
    assert len(await _radcheck_rows(session, "bob", RAD_AUTH_TYPE_ATTRIBUTE)) == 0

    await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, status="suspended"
    )
    reject = await _radcheck_rows(session, "bob", RAD_AUTH_TYPE_ATTRIBUTE)
    assert len(reject) == 1
    assert reject[0].Value == "Reject"

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
    assert {r.Attribute for r in rows} == {RAD_PASSWORD_ATTRIBUTE}


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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/unit/test_subscribers_service.py -v
```

Expected: FAIL — `AttributeError: module 'app.services.subscribers' has no attribute 'update_subscriber'`.

- [ ] **Step 3: Implement**

Append to `backend/app/services/subscribers.py` (import `delete` alongside the other sqlalchemy names):

```python
async def _upsert_password(session: AsyncSession, username: str, password: str) -> None:
    """Set (or create) the Cleartext-Password check row for a subscriber."""
    row = (
        await session.execute(
            select(RadCheck).where(
                RadCheck.UserName == username,
                RadCheck.Attribute == RAD_PASSWORD_ATTRIBUTE,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            RadCheck(
                UserName=username,
                Attribute=RAD_PASSWORD_ATTRIBUTE,
                op=RAD_OP_SET,
                Value=password,
            )
        )
    else:
        row.Value = password


async def _set_reject(session: AsyncSession, username: str, *, reject: bool) -> None:
    """Add or remove the Auth-Type := Reject check row per the subscriber's status."""
    row = (
        await session.execute(
            select(RadCheck).where(
                RadCheck.UserName == username,
                RadCheck.Attribute == RAD_AUTH_TYPE_ATTRIBUTE,
            )
        )
    ).scalar_one_or_none()
    if reject and row is None:
        session.add(_reject_check(username))
    elif not reject and row is not None:
        await session.delete(row)


async def update_subscriber(
    session: AsyncSession,
    subscriber: Subscriber,
    *,
    actor_id: int,
    full_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> Subscriber:
    """Apply profile changes; password and status changes sync radcheck rows."""
    changed: list[str] = []
    if full_name is not None and full_name != subscriber.full_name:
        subscriber.full_name = full_name
        changed.append("full_name")
    if email is not None and email != subscriber.email:
        subscriber.email = email
        changed.append("email")
    if phone is not None and phone != subscriber.phone:
        subscriber.phone = phone
        changed.append("phone")
    if notes is not None and notes != subscriber.notes:
        subscriber.notes = notes
        changed.append("notes")
    if password is not None:
        await _upsert_password(session, subscriber.username, password)
        changed.append("password")
    if status is not None and status != subscriber.status:
        subscriber.status = status
        await _set_reject(session, subscriber.username, reject=status != ACTIVE_STATUS)
        changed.append("status")

    if changed:
        await _commit_or_conflict(session, "Username already exists")
        await audit_service.record_audit(
            session,
            admin_id=actor_id,
            action="update",
            resource="subscribers",
            resource_id=str(subscriber.id),
            metadata_={"username": subscriber.username, "fields": changed},
        )
    return subscriber


async def delete_subscriber(session: AsyncSession, subscriber: Subscriber, actor_id: int) -> None:
    """Delete the profile and every radcheck row for its username in one transaction."""
    username = subscriber.username
    subscriber_id = subscriber.id
    await session.execute(delete(RadCheck).where(RadCheck.UserName == username))
    await session.delete(subscriber)
    await session.commit()
    await audit_service.record_audit(
        session,
        admin_id=actor_id,
        action="delete",
        resource="subscribers",
        resource_id=str(subscriber_id),
        metadata_={"username": username},
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_subscribers_service.py -v
```

Expected: PASS — 10 tests total (4 new). Update the import line to `from sqlalchemy import delete, func, or_, select` if ruff flags the missing `delete`.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/services/subscribers.py tests/unit/test_subscribers_service.py
git commit -m "feat: subscriber update/delete with radcheck password and status sync"
```

---

### Task 4: Subscribers API + integration coverage

**Files:**
- Create: `backend/app/api/v1/subscribers.py`
- Modify: `backend/app/api/v1/router.py` (include the router)
- Test: `backend/tests/integration/test_subscribers.py`

**Interfaces:**
- `GET /api/v1/subscribers` — `subscribers:read`; `Page[SubscriberOut]`; `page` (≥1), `page_size` (1–100), `q` (≤64, optional).
- `POST /api/v1/subscribers` — `subscribers:write`; 201 + `SubscriberOut`.
- `GET /api/v1/subscribers/{subscriber_id}` — `subscribers:read`.
- `PATCH /api/v1/subscribers/{subscriber_id}` — `subscribers:write`; password → radcheck upsert, status → Reject sync.
- `DELETE /api/v1/subscribers/{subscriber_id}` — `subscribers:delete`; 204.
- Rate limits: `subscriber_read` on reads, `subscriber_write` on writes (every limited endpoint declares `request` + `response` params — slowapi requirement).
- Every route docstring states its permission string (CLAUDE.md convention).

- [ ] **Step 1: Write the failing integration tests**

Create `backend/tests/integration/test_subscribers.py`:

```python
from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.radius import RadCheck
from app.models.rbac import Admin, Permission, Role
from app.models.subscriber import Subscriber


async def _seed_admin(session, username, codes) -> Admin:
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


async def _login(client, username="boss"):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _radcheck_rows(session, username: str, attribute: str | None = None) -> list[RadCheck]:
    stmt = select(RadCheck).where(RadCheck.UserName == username)
    if attribute is not None:
        stmt = stmt.where(RadCheck.Attribute == attribute)
    return list((await session.execute(stmt)).scalars().all())


async def test_superadmin_full_lifecycle(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)

    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob Subscriber", "password": "radpass123"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    subscriber_id = body["id"]
    assert body["username"] == "bob"
    assert body["status"] == "active"
    assert body["plan_id"] is None

    # radcheck carries the credential
    password_rows = await _radcheck_rows(session, "bob", "Cleartext-Password")
    assert len(password_rows) == 1
    assert password_rows[0].Value == "radpass123"

    resp = await client.get("/api/v1/subscribers", headers=_auth(token))
    assert resp.status_code == 200
    assert "bob" in [s["username"] for s in resp.json()["items"]]

    resp = await client.get(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))
    assert resp.status_code == 200

    # password change upserts radcheck
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}",
        json={"email": "bob@netgrid.local", "password": "newpass456"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    password_rows = await _radcheck_rows(session, "bob", "Cleartext-Password")
    assert len(password_rows) == 1
    assert password_rows[0].Value == "newpass456"

    # suspend adds the Reject row; reactivate removes it
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"status": "suspended"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert len(await _radcheck_rows(session, "bob", "Auth-Type")) == 1
    resp = await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"status": "active"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert len(await _radcheck_rows(session, "bob", "Auth-Type")) == 0

    # delete removes profile + radcheck rows
    resp = await client.delete(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))
    assert resp.status_code == 204, resp.text
    assert (
        await session.execute(select(Subscriber).where(Subscriber.id == subscriber_id))
    ).scalar_one_or_none() is None
    assert await _radcheck_rows(session, "bob") == []


async def test_create_with_status_suspended(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob", "password": "radpass123", "status": "suspended"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    assert len(await _radcheck_rows(session, "bob", "Auth-Type")) == 1


async def test_duplicate_username_409(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    payload = {"username": "bob", "full_name": "Bob", "password": "radpass123"}
    assert (
        await client.post("/api/v1/subscribers", json=payload, headers=_auth(token))
    ).status_code == 201
    resp = await client.post("/api/v1/subscribers", json=payload, headers=_auth(token))
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_invalid_status_422(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob", "password": "radpass123", "status": "banana"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


async def test_auditor_read_only(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    super_token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob", "password": "radpass123"},
        headers=_auth(super_token),
    )
    subscriber_id = resp.json()["id"]

    await _seed_admin(session, "audit", ["*:read"])
    token = await _login(client, "audit")
    for method, path in [
        ("get", "/api/v1/subscribers"),
        ("get", f"/api/v1/subscribers/{subscriber_id}"),
    ]:
        resp = await client.request(method, path, headers=_auth(token))
        assert resp.status_code == 200, (method, path, resp.text)

    for method, path, body in [
        ("post", "/api/v1/subscribers", {"username": "x", "full_name": "X", "password": "radpass123"}),
        ("patch", f"/api/v1/subscribers/{subscriber_id}", {"status": "suspended"}),
        ("delete", f"/api/v1/subscribers/{subscriber_id}", None),
    ]:
        resp = await client.request(method, path, json=body, headers=_auth(token))
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_without_permission_denied(client, session):
    await _seed_admin(session, "boss", ["plans:read"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "x", "full_name": "X", "password": "radpass123"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


async def test_404_unknown_subscriber(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.get("/api/v1/subscribers/999", headers=_auth(token))
    assert resp.status_code == 404
    # PATCH needs a body (even an empty one) or FastAPI 422s before the handler's 404
    resp = await client.patch("/api/v1/subscribers/999", json={}, headers=_auth(token))
    assert resp.status_code == 404
    resp = await client.delete("/api/v1/subscribers/999", headers=_auth(token))
    assert resp.status_code == 404


async def test_audit_entries_written(client, session):
    await _seed_admin(session, "boss", ["*:*"])
    token = await _login(client)
    resp = await client.post(
        "/api/v1/subscribers",
        json={"username": "bob", "full_name": "Bob", "password": "radpass123"},
        headers=_auth(token),
    )
    subscriber_id = resp.json()["id"]
    await client.patch(
        f"/api/v1/subscribers/{subscriber_id}", json={"status": "suspended"}, headers=_auth(token)
    )
    await client.delete(f"/api/v1/subscribers/{subscriber_id}", headers=_auth(token))

    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    actions = {(row.action, row.resource) for row in rows}
    assert ("create", "subscribers") in actions
    assert ("update", "subscribers") in actions
    assert ("delete", "subscribers") in actions
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/integration/test_subscribers.py -v
```

Expected: FAIL — `404` on every route (`app/api/v1/subscribers.py` doesn't exist / router not included).

- [ ] **Step 3: Implement**

Create `backend/app/api/v1/subscribers.py`:

```python
"""Subscriber management endpoints (Phase 5).

Permissions: subscribers:read for listing/reading, subscribers:write for
create/update, subscribers:delete for removal. Credential and status changes
write radcheck in the same transaction as the profile row (direct coupling).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.db import get_session
from app.core.pagination import Page
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.subscribers import SubscriberCreate, SubscriberOut, SubscriberUpdate
from app.services import subscribers as subscribers_service

router = APIRouter(prefix="/subscribers", tags=["subscribers"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=Page[SubscriberOut])
@limiter.limit(LIMITS["subscriber_read"])
async def list_subscribers(
    request: Request,
    response: Response,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("subscribers:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=64),
) -> Page[SubscriberOut]:
    """GET /api/v1/subscribers — requires subscribers:read."""
    items, total = await subscribers_service.list_subscribers(session, page, page_size, q)
    return Page(
        items=[SubscriberOut.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SubscriberOut, status_code=201)
@limiter.limit(LIMITS["subscriber_write"])
async def create_subscriber(
    request: Request,
    response: Response,
    payload: SubscriberCreate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("subscribers:write"))],
) -> SubscriberOut:
    """POST /api/v1/subscribers — requires subscribers:write."""
    subscriber = await subscribers_service.create_subscriber(
        session, actor_id=actor.id, **payload.model_dump()
    )
    return SubscriberOut.model_validate(subscriber)


@router.get("/{subscriber_id}", response_model=SubscriberOut)
@limiter.limit(LIMITS["subscriber_read"])
async def get_subscriber(
    request: Request,
    response: Response,
    subscriber_id: int,
    session: SessionDep,
    _: Annotated[Admin, Depends(require_permission("subscribers:read"))],
) -> SubscriberOut:
    """GET /api/v1/subscribers/{id} — requires subscribers:read."""
    subscriber = await subscribers_service.get_subscriber_or_404(session, subscriber_id)
    return SubscriberOut.model_validate(subscriber)


@router.patch("/{subscriber_id}", response_model=SubscriberOut)
@limiter.limit(LIMITS["subscriber_write"])
async def update_subscriber(
    request: Request,
    response: Response,
    subscriber_id: int,
    payload: SubscriberUpdate,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("subscribers:write"))],
) -> SubscriberOut:
    """PATCH /api/v1/subscribers/{id} — requires subscribers:write.

    Changing the password updates the radcheck Cleartext-Password row;
    changing the status adds/removes the radcheck Auth-Type := Reject row.
    """
    subscriber = await subscribers_service.get_subscriber_or_404(session, subscriber_id)
    subscriber = await subscribers_service.update_subscriber(
        session, subscriber, actor_id=actor.id, **payload.model_dump(exclude_unset=True)
    )
    return SubscriberOut.model_validate(subscriber)


@router.delete("/{subscriber_id}", status_code=204)
@limiter.limit(LIMITS["subscriber_write"])
async def delete_subscriber(
    request: Request,
    response: Response,
    subscriber_id: int,
    session: SessionDep,
    actor: Annotated[Admin, Depends(require_permission("subscribers:delete"))],
) -> Response:
    """DELETE /api/v1/subscribers/{id} — requires subscribers:delete.

    Removes the profile and every radcheck row for the username.
    """
    subscriber = await subscribers_service.get_subscriber_or_404(session, subscriber_id)
    await subscribers_service.delete_subscriber(session, subscriber, actor.id)
    return Response(status_code=204)
```

Modify `backend/app/api/v1/router.py`:

```python
from .roles import permissions_router
from .roles import router as roles_router
from .subscribers import router as subscribers_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(admins_router)
api_router.include_router(roles_router)
api_router.include_router(permissions_router)
api_router.include_router(subscribers_router)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/integration/test_subscribers.py -v
```

Expected: PASS — 8 tests (full lifecycle incl. radcheck verification, suspended-on-create, 409, 422, auditor read-only, missing-permission 403, 404s, audit rows). Requires Postgres + Redis running.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/api/v1/subscribers.py app/api/v1/router.py tests/integration/test_subscribers.py
git commit -m "feat: add subscribers API with RBAC gating"
```

---

### Task 5: Full gates + CLAUDE.md sync + live verification (incl. radtest)

**Files:**
- Modify: `CLAUDE.md` (check off Phase 5, record the radcheck coupling contract)

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

Expected: ruff clean, mypy clean, full suite green (previous 112 tests + the new model/service/integration tests).

- [ ] **Step 2: Update `CLAUDE.md`**

Apply exactly these changes:

1. In `Build Phases`, check off **Phase 5 — Subscribers CRUD + RADIUS credential coupling**: change `- [ ]` to `- [x]`.
2. In the `FreeRADIUS ↔ database coupling: decision` section, append one bullet:

```
- Phase 5 implementation: subscriber credentials are written straight to `radcheck` in the same transaction as the `subscribers` row — one `Cleartext-Password` check per username (op `:=`), plus an `Auth-Type := Reject` check whenever the subscriber's status is not `active` (`active` | `suspended` | `expired`). Usernames are immutable after creation (renaming would rewrite radcheck rows). Plan assignment writes `radusergroup` and lands with Phase 6; until then `subscribers.plan_id` stays NULL.
```

- [ ] **Step 3: Live verification against the running stack**

Rebuild the backend image (it predates this code) and verify the full RADIUS path — the ultimate proof of the coupling is FreeRADIUS itself authenticating the new subscriber:

```bash
docker compose up -d postgres redis freeradius
docker compose up -d --build backend
sleep 5
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"superadmin","password":"netgrid-admin"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

# 1. create a subscriber -> radcheck row
SUB=$(curl -s -X POST http://localhost:8000/api/v1/subscribers -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"username":"p5test","full_name":"Plan Five Tester","password":"radpass123"}')
echo "$SUB"
SUB_ID=$(echo "$SUB" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT \"UserName\", \"Attribute\", op, \"Value\" FROM radcheck WHERE \"UserName\"='p5test';"
# expect: one row, Cleartext-Password := radpass123

# 2. REAL RADIUS auth — expect Access-Accept
docker compose exec freeradius radtest p5test radpass123 127.0.0.1 0 testing123

# 3. suspend -> Auth-Type := Reject row; radtest now rejects
curl -s -X PATCH http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"status":"suspended"}'
docker compose exec freeradius radtest p5test radpass123 127.0.0.1 0 testing123
# expect: Access-Reject (exit code non-zero is correct for a reject)

# 4. reactivate -> Reject row gone; radtest accepts again
curl -s -X PATCH http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"status":"active"}'
docker compose exec freeradius radtest p5test radpass123 127.0.0.1 0 testing123

# 5. delete -> radcheck rows gone
curl -s -o /dev/null -w "delete: %{http_code}\n" \
  -X DELETE http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH"
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT count(*) FROM radcheck WHERE \"UserName\"='p5test';"
# expect: 0
```

Expected: create → radcheck row present → **radtest Access-Accept** → suspend → **radtest Access-Reject** → reactivate → Accept → delete → radcheck empty. If radtest shows `Access-Reject` on step 2, check the freeradius logs (`docker compose logs freeradius | tail -30`) before assuming the app is wrong — the sql module reads `radcheck` directly, so a miss usually means the row/secret mismatch.

- [ ] **Step 4: Final commit**

```bash
cd ..
git add CLAUDE.md
git commit -m "docs: check off Phase 5, record radcheck coupling in CLAUDE.md"
```

---

## Self-Review (to verify when implementing)

- **Spec coverage:** every Phase 5 deliverable from CLAUDE.md maps to a task — subscribers CRUD (T2–T4), service-layer radcheck writes in the same transaction as `subscribers` (T2/T3), radcheck rows created/updated/deleted correctly (T2/T3 unit + T4 integration), RBAC-gated endpoints with explicit permissions in docstrings (T4). The testing table's "service-layer validation" (T2/T3) and "full CRUD via API, radcheck row created/updated/deleted correctly" (T4) rows are both covered.
- **Placeholder scan:** no TBD/TODO; every code step carries full content. No migration hash placeholders — this phase ships zero migrations (radcheck is FreeRADIUS-owned; `subscribers:*` permissions already seeded).
- **Layering compliance:** routers are thin (parse/validate → call services); all DB access lives in `services/subscribers.py`; services never import from `api/`; the radcheck sync helpers are private to the service. `require_permission` comes from `app/api/deps.py` unchanged.
- **Type consistency:** single constants module for the radcheck contract (`RAD_PASSWORD_ATTRIBUTE`, `RAD_AUTH_TYPE_ATTRIBUTE`, `RAD_REJECT_VALUE`, `RAD_OP_SET`) shared by service and tests; `SubscriberCreate`/`Update`/`Out` are the only subscriber payload types; `status` is `Literal["active","suspended","expired"]` everywhere.
- **Known ripples:**
  - `SubscriberOut.plan_id` is always `None` until Phase 6 — by design (setting it without `radusergroup` would violate the coupling invariant). Phase 6 must add `plan_id` to create/update schemas **and** write `radusergroup` in the same transaction.
  - Phase 6 also owns `radusergroup` cleanup on subscriber delete (Phase 5 never writes that table, so `delete_subscriber` only clears radcheck — when Phase 6 lands, extend the delete to purge `radusergroup` rows too).
  - radcheck stores the subscriber password as cleartext — required by FreeRADIUS PAP/MSCHAPv2; documented in CLAUDE.md. The `subscribers` table never holds credentials.
  - Test DB builds `radcheck` from the model via `create_all` — conftest needs no changes; CI needs no changes (postgres + redis already provisioned in the backend job; the freeradius job only matters for Task 5's manual radtest, which is not part of pytest).
  - `delete_subscriber` uses a bulk `delete()` on radcheck rather than ORM objects — no lazy-load hazards; the profile row is deleted with `session.delete`.
- **Out of scope by design (later phases):** plan assignment / `radusergroup` (Phase 6), NAS devices (Phase 7), tiered rate-limit rework (Phase 8), sessions/CoA (Phase 9), billing (Phase 10), FreeRADIUS abuse protection + scripted `/tests/radius` radtest checks (Phase 11), frontend dashboard (Phase 12).
