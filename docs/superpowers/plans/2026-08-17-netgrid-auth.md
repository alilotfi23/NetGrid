# NetGrid Auth Implementation Plan (Plan 2 of 5 — Day 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin authentication for the NetGrid dashboard: argon2 password hashing, JWT access + refresh tokens, a login/refresh/logout/me API, and auth-focused rate limiting (login 5/min/IP) — all with full unit + integration coverage per the CLAUDE.md testing table. This is **authentication only**; RBAC/permissions arrive in Plan 3 on top of the `get_current_admin` dependency built here. Prerequisite: Plan 1 committed (foundation, models, conventions layer, Phases 0/1/4 checked off in CLAUDE.md).

**Architecture:** Passwords hashed with `passlib` `CryptContext(schemes=["argon2"])` (pinned in CLAUDE.md). Tokens are HS256 JWTs (`PyJWT`) with claims `sub` (admin id), `type` (`access`|`refresh`), `jti` (unique id), `iat`, `exp`. Access tokens live 15 min (`JWT_ACCESS_TTL_MINUTES`), refresh tokens 7 days (`JWT_REFRESH_TTL_DAYS`). Refresh tokens are **rotated** on every refresh (old `jti` blacklisted), and logout **revokes** by blacklisting the presented refresh token's `jti`. The blacklist lives in Redis under `token:blacklist:<jti>` with a TTL equal to the token's remaining life. API rate limiting uses `slowapi` backed by Redis, centralized in `app/core/rate_limit.py` with a `key_prefix="netgrid-rl"` so tests can `limiter.reset()` without touching other Redis data. Every error keeps the Plan 1 envelope `{"error": {"code", "message"}}`; rate-limit responses use `429` + `Retry-After` + code `RATE_LIMITED`.

**Tech Stack additions:** `passlib[argon2]` + `argon2-cffi` (verified compatible: passlib 1.7.4 + argon2-cffi 25.1.0 hash/verify roundtrip passes on Python 3.14), `PyJWT`, `slowapi` (pulls `limits`). `redis` is already a dependency. Postgres + Redis containers must be running for every task after Task 1.

## Global Constraints

- Same as Plan 1: async all the way down; `/api/v1` routes; `{"error": {"code", "message"}}` envelope; routers thin → services own DB access; services never import from `api/`; real Postgres for tests; ruff + `mypy --strict` on `app/` clean before every commit; Conventional Commits; commit at the end of every task.
- **New:** tests that exercise auth endpoints need Redis (rate limiter + blacklist) and Postgres (admins table). Start `docker compose up -d postgres redis` before Task 2 and leave them running through Task 5.
- Auth endpoints (`/api/v1/auth/*`) are the documented pre-RBAC exception to "every endpoint needs an explicit permission check" (see CLAUDE.md Phase 3) — they *are* the authentication layer. Plan 3 adds `require_permission` to `/auth/me` and everything else.
- Every limited endpoint must declare both `request: Request` and `response: Response` parameters — slowapi keys on the request's client IP and injects `X-RateLimit-*` / `Retry-After` headers through the response parameter. Without them, slowapi raises at runtime.
- Do not add RBAC, permission claims, or role resolution in this plan — that is Plan 3 and will add claims/claims-versioning then.

## File Structure

```
/backend
  pyproject.toml            # + passlib[argon2], argon2-cffi, pyjwt, slowapi
  app/
    core/
      redis.py              # NEW get_redis() — fresh client per call (loop-bound pools)
      rate_limit.py         # NEW slowapi Limiter + 429 handler + LIMITS dict
      security.py           # NEW password hashing + JWT primitives
    api/
      deps.py               # NEW get_current_admin dependency
      v1/
        auth.py             # NEW login / refresh / logout / me
        router.py           # MODIFIED — include auth router
    schemas/
      __init__.py           # NEW (empty)
      auth.py               # NEW LoginRequest, TokenPair, AdminOut, ...
    services/
      __init__.py           # NEW (empty)
      auth.py               # NEW authenticate_admin, refresh_tokens, logout, ...
  tests/
    conftest.py             # MODIFIED — app + client fixtures (memory reset, dep override)
    unit/
      test_security.py      # NEW — hashing + token unit tests
      test_auth_service.py  # NEW — service layer tests
    integration/
      test_auth.py          # NEW — login/refresh/logout/me flows
      test_rate_limit.py    # NEW — 429 threshold, per-IP isolation, window reset
  alembic/                  # NO migration — admins table already exists from Plan 1
```

No settings changes: `jwt_secret`, `jwt_access_ttl_minutes`, `jwt_refresh_ttl_days` already exist in `app/core/config.py` and `.env.example`. No Alembic migration is needed (no schema change).

---

### Task 1: Password hashing + JWT primitives (`app/core/security.py`)

**Files:**
- Modify: `backend/pyproject.toml` (add 4 deps)
- Create: `backend/app/core/security.py`
- Test: `backend/tests/unit/test_security.py`

**Interfaces:**
- `hash_password(password: str) -> str` — argon2 hash via `CryptContext`.
- `verify_password(plain: str, hashed: str) -> bool`.
- `create_access_token(subject: str) -> str` — token with `type="access"`, TTL from `jwt_access_ttl_minutes`.
- `create_refresh_token(subject: str) -> tuple[str, str]` — returns `(token, jti)`; TTL from `jwt_refresh_ttl_days`.
- `decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]` — raises `UnauthorizedError` (401 envelope) on invalid signature, expiry, or wrong `type` claim.

- [ ] **Step 1: Add dependencies**

In `backend/pyproject.toml` `[project].dependencies` (keep existing entries):

```toml
    "passlib[argon2]>=1.7.4",
    "argon2-cffi>=23.1",
    "pyjwt>=2.8",
    "slowapi>=0.1.9",
```

```bash
cd backend
source .venv/Scripts/activate
pip install -e ".[dev]"
python -c "import passlib, argon2, jwt, slowapi; print('deps ok')"
```

Expected: `deps ok`. (Verified upstream: passlib 1.7.4 + argon2-cffi 25.1.0 hash/verify works on Python 3.14 — no compat pin needed.)

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/test_security.py`:

```python
import jwt
import pytest

from app.core import security
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError


def test_password_hash_roundtrip():
    hashed = security.hash_password("s3cret")
    assert hashed != "s3cret"
    assert security.verify_password("s3cret", hashed)


def test_password_hash_is_salted():
    assert security.hash_password("same") != security.hash_password("same")


def test_wrong_password_rejected():
    hashed = security.hash_password("right")
    assert not security.verify_password("wrong", hashed)


def test_access_token_roundtrip():
    token = security.create_access_token("7")
    payload = security.decode_token(token, expected_type="access")
    assert payload["sub"] == "7"
    assert payload["type"] == "access"
    assert payload["jti"]
    assert payload["exp"]


def test_refresh_token_roundtrip_returns_jti():
    token, jti = security.create_refresh_token("7")
    payload = security.decode_token(token, expected_type="refresh")
    assert payload["sub"] == "7"
    assert payload["jti"] == jti


def test_decode_rejects_wrong_type():
    token = security.create_access_token("7")
    with pytest.raises(UnauthorizedError):
        security.decode_token(token, expected_type="refresh")


def test_decode_rejects_wrong_secret():
    settings = get_settings()
    token = jwt.encode({"sub": "7"}, "not-the-secret", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        security.decode_token(token)


def test_decode_rejects_expired_token():
    settings = get_settings()
    expired = jwt.encode(
        {"sub": "7", "type": "access", "jti": "x", "iat": 0, "exp": 0},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        security.decode_token(expired)


def test_decode_rejects_garbage():
    with pytest.raises(UnauthorizedError):
        security.decode_token("not.a.jwt")
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/unit/test_security.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.security'`.

- [ ] **Step 4: Implement**

Create `backend/app/core/security.py`:

```python
"""Password hashing (argon2) and JWT primitives for admin auth."""
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from .config import get_settings
from .exceptions import UnauthorizedError

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _encode(subject: str, token_type: str, ttl: timedelta) -> tuple[str, str]:
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
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, jti


def create_access_token(subject: str) -> str:
    ttl = timedelta(minutes=get_settings().jwt_access_ttl_minutes)
    token, _ = _encode(subject, TOKEN_TYPE_ACCESS, ttl)
    return token


def create_refresh_token(subject: str) -> tuple[str, str]:
    """Returns (token, jti). The jti is what logout/rotation blacklists."""
    ttl = timedelta(days=get_settings().jwt_refresh_ttl_days)
    return _encode(subject, TOKEN_TYPE_REFRESH, ttl)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Decode + validate a JWT. Raises UnauthorizedError on any failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
    if expected_type is not None and payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")
    return payload
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/unit/test_security.py -v
```

Expected: PASS (9 tests).

- [ ] **Step 6: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add pyproject.toml app/core/security.py tests/unit/test_security.py
git commit -m "feat: add argon2 password hashing and JWT primitives"
```

---

### Task 2: Redis client + rate limiting foundation

**Files:**
- Create: `backend/app/core/redis.py`, `backend/app/core/rate_limit.py`
- Modify: `backend/app/main.py` (set `app.state.limiter`, register 429 handler)
- Test: `backend/tests/integration/test_rate_limit.py`

**Interfaces:**
- `app.core.redis.get_redis() -> redis.asyncio.Redis` — **fresh client per call** (Redis pools are event-loop-bound; a singleton would leak across pytest loops, same failure mode as the Plan 1 asyncpg fix). Callers `await redis.aclose()` when done.
- `app.core.rate_limit.limiter` — module-level `slowapi.Limiter`, Redis-backed, `key_prefix="netgrid-rl"`, `headers_enabled=True`.
- `app.core.rate_limit.LIMITS` — `{"login": "5/minute", "refresh": "10/minute", "logout": "10/minute", "me": "60/minute"}` — the single home for limit strings (CLAUDE.md: no magic numbers per router).
- `app.core.rate_limit.register_rate_limit_handler(app)` — 429 handler returning the error envelope + `Retry-After` (delegates header injection to slowapi's `_inject_headers`).
- `create_app()` now sets `app.state.limiter = limiter` and calls `register_rate_limit_handler(app)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_rate_limit.py`:

```python
import asyncio

from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.models.rbac import Admin

LOGIN = {"username": "root", "password": "wrong"}


async def _seed_admin(session):
    session.add(
        Admin(
            username="root",
            email="root@netgrid.local",
            password_hash=hash_password("secret123"),
            is_active=True,
        )
    )
    await session.commit()


async def test_login_locked_out_after_threshold(app, session):
    await _seed_admin(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.post("/api/v1/auth/login", json=LOGIN)
            assert resp.status_code == 401
        resp = await client.post("/api/v1/auth/login", json=LOGIN)
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "RATE_LIMITED"
        assert resp.headers.get("Retry-After") is not None


async def test_rate_limit_is_per_ip(app, session):
    await _seed_admin(session)
    client_a = AsyncClient(transport=ASGITransport(app=app, client=("10.1.1.1", 1)), base_url="http://test")
    client_b = AsyncClient(transport=ASGITransport(app=app, client=("10.2.2.2", 2)), base_url="http://test")
    async with client_a, client_b:
        for _ in range(5):
            assert (await client_a.post("/api/v1/auth/login", json=LOGIN)).status_code == 401
            assert (await client_b.post("/api/v1/auth/login", json=LOGIN)).status_code == 401
        # 6th request from A is blocked; B is unaffected
        assert (await client_a.post("/api/v1/auth/login", json=LOGIN)).status_code == 429
        assert (await client_b.post("/api/v1/auth/login", json=LOGIN)).status_code == 401


async def test_limit_resets_after_window(app):
    @app.get("/api/v1/scratch")
    @limiter.limit("2/second")
    async def scratch(request, response):
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/scratch")).status_code == 200
        assert (await client.get("/api/v1/scratch")).status_code == 200
        assert (await client.get("/api/v1/scratch")).status_code == 429
        await asyncio.sleep(1.2)
        assert (await client.get("/api/v1/scratch")).status_code == 200
```

> The `app` and `session` fixtures come from the conftest change in Step 3 (below). `test_limit_resets_after_window` is mildly timing-sensitive (fixed-window 1s); if it flakes in CI, raise the sleep to 1.5s — do not weaken the 429 assertions.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
source .venv/Scripts/activate
pytest tests/integration/test_rate_limit.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.rate_limit'` (and missing `app` fixture).

- [ ] **Step 3: Add the `app` + `client` fixtures to `backend/tests/conftest.py`**

Append to the existing conftest (keep the existing `engine`/`session` fixtures):

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.rate_limit import limiter as app_limiter
from app.main import create_app


@pytest_asyncio.fixture
async def app(session):
    """Fresh FastAPI app per test, wired to the test DB session.

    Rate-limit counters persist in Redis between tests, so the netgrid-rl
    namespace is reset first; blacklist keys are unique per token and expire,
    so they need no cleanup.
    """
    test_app = create_app()
    app_limiter.reset()
    test_app.dependency_overrides[get_session] = lambda: session
    yield test_app
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

> `app_limiter.reset()` clears only keys under the `netgrid-rl` prefix (RedisStorage Lua clear), so it is safe and deterministic. If a future storage change makes reset unsupported, replace it with a scan+delete of `netgrid-rl:*`.

- [ ] **Step 4: Implement**

Create `backend/app/core/redis.py`:

```python
"""Async Redis client for short-lived caches and token revocation."""
from redis.asyncio import Redis

from .config import get_settings


def get_redis() -> Redis:
    """Return a fresh Redis client.

    Connection pools are bound to the event loop that created them, so a
    module-level singleton would leak across test loops (same failure mode as
    the Plan 1 asyncpg engine fix). Callers must ``await redis.aclose()``.
    """
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
```

Create `backend/app/core/rate_limit.py`:

```python
"""Centralized API rate limiting (slowapi + Redis).

Auth endpoints get strict limits (see CLAUDE.md Rate Limiting). Phase 8
expands this module to tiered limits across all routes — limits stay here,
never scattered as magic numbers per router.
"""
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from .config import get_settings

# key_prefix namespaces limiter keys so tests can limiter.reset() the whole
# namespace without touching any other Redis data.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().redis_url,
    headers_enabled=True,
    key_prefix="netgrid-rl",
)

LIMITS = {
    "login": "5/minute",
    "refresh": "10/minute",
    "logout": "10/minute",
    "me": "60/minute",
}


def register_rate_limit_handler(app: FastAPI) -> None:
    """429 handler matching the project error envelope + Retry-After header."""

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
        response: Response = JSONResponse(
            status_code=429,
            content={
                "error": {"code": "RATE_LIMITED", "message": "Rate limit exceeded, try again later"}
            },
        )
        view_limit = getattr(request.state, "view_rate_limit", None)
        if view_limit is not None:
            # request.app is typed ASGIApp; cast to FastAPI for mypy --strict.
            response = cast(FastAPI, request.app).state.limiter._inject_headers(response, view_limit)
        return response
```

Modify `backend/app/main.py` to:

```python
from fastapi import FastAPI

from .api.v1.router import api_router
from .core.errors import register_exception_handlers
from .core.rate_limit import limiter, register_rate_limit_handler


def create_app() -> FastAPI:
    app = FastAPI(title="NetGrid API", version="0.1.0")
    app.include_router(api_router, prefix="/api/v1")
    register_exception_handlers(app)
    app.state.limiter = limiter
    register_rate_limit_handler(app)
    return app


app = create_app()
```

- [ ] **Step 5: Run the tests to verify they pass**

Requires Redis + Postgres running: `docker compose up -d postgres redis` (from repo root).

```bash
pytest tests/integration/test_rate_limit.py -v
```

Expected: PASS (3 tests). If `test_login_locked_out_after_threshold` fails at the 6th request with 401 instead of 429, the limiter's Redis storage is not being hit — check `docker compose ps redis` and that `REDIS_URL`/`redis_url` default is reachable.

- [ ] **Step 6: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/core/redis.py app/core/rate_limit.py app/main.py tests/conftest.py tests/integration/test_rate_limit.py
git commit -m "feat: add Redis-backed API rate limiting with error envelope"
```

---

### Task 3: Auth service layer (`app/services/auth.py`)

**Files:**
- Create: `backend/app/services/__init__.py` (empty), `backend/app/services/auth.py`
- Test: `backend/tests/unit/test_auth_service.py`

**Interfaces:**
- `get_admin_by_id(session, admin_id) -> Admin | None` — used by the API dependency and refresh; keeps DB access in the service layer.
- `authenticate_admin(session, username, password) -> Admin` — raises `UnauthorizedError("Invalid username or password")` for unknown user, wrong password, or inactive admin (same message: don't leak which).
- `build_token_pair(admin) -> dict[str, str]` — `{"access_token", "refresh_token", "token_type": "bearer"}`.
- `refresh_tokens(session, refresh_token) -> dict[str, str]` — decode (refresh type), reject if blacklisted, load admin (must exist + active), blacklist the old `jti` (rotation), return a fresh pair.
- `logout(refresh_token) -> None` — decode (refresh type), blacklist its `jti` for the token's remaining lifetime.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_auth_service.py`:

```python
import pytest

from app.core import security
from app.core.exceptions import UnauthorizedError
from app.core.security import hash_password
from app.models.rbac import Admin
from app.services import auth as auth_service


async def _seed_admin(session, username="root", password="secret123", is_active=True) -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password(password),
        is_active=is_active,
    )
    session.add(admin)
    await session.commit()
    return admin


async def test_authenticate_success(session):
    await _seed_admin(session)
    admin = await auth_service.authenticate_admin(session, "root", "secret123")
    assert admin.username == "root"


async def test_authenticate_wrong_password(session):
    await _seed_admin(session)
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_admin(session, "root", "wrong")


async def test_authenticate_unknown_user(session):
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_admin(session, "ghost", "secret123")


async def test_authenticate_inactive_admin(session):
    await _seed_admin(session, is_active=False)
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_admin(session, "root", "secret123")


async def test_refresh_rotates_and_blacklists_old_token(session):
    admin = await _seed_admin(session)
    old_token, _ = security.create_refresh_token(str(admin.id))
    pair = await auth_service.refresh_tokens(session, old_token)
    assert pair["access_token"]
    assert pair["refresh_token"] != old_token
    with pytest.raises(UnauthorizedError):  # old token is now rotated away
        await auth_service.refresh_tokens(session, old_token)


async def test_refresh_rejects_garbage(session):
    await _seed_admin(session)
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(session, "not-a-token")


async def test_logout_blacklists_refresh_token(session):
    admin = await _seed_admin(session)
    token, _ = security.create_refresh_token(str(admin.id))
    await auth_service.logout(token)
    with pytest.raises(UnauthorizedError):
        await auth_service.refresh_tokens(session, token)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/unit/test_auth_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Implement**

Create empty `backend/app/services/__init__.py`.

Create `backend/app/services/auth.py`:

```python
"""Admin authentication service: credential checks, token issuance, revocation."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.rbac import Admin

BLACKLIST_KEY = "token:blacklist:{}"


async def get_admin_by_id(session: AsyncSession, admin_id: int) -> Admin | None:
    return await session.get(Admin, admin_id)


async def authenticate_admin(session: AsyncSession, username: str, password: str) -> Admin:
    """Verify credentials; returns the Admin or raises UnauthorizedError."""
    result = await session.execute(select(Admin).where(Admin.username == username))
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active or not verify_password(password, admin.password_hash):
        raise UnauthorizedError("Invalid username or password")
    return admin


def build_token_pair(admin: Admin) -> dict[str, str]:
    access = create_access_token(str(admin.id))
    refresh, _ = create_refresh_token(str(admin.id))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def _jti_ttl_seconds(payload: dict) -> int:
    """Remaining life of a token in seconds, min 1 (PyJWT decodes exp to int)."""
    exp = int(payload["exp"])
    now = int(datetime.now(UTC).timestamp())
    return max(exp - now, 1)


async def _revoke_jti(jti: str, ttl_seconds: int) -> None:
    redis = get_redis()
    try:
        await redis.set(BLACKLIST_KEY.format(jti), "1", ex=ttl_seconds)
    finally:
        await redis.aclose()


async def _is_blacklisted(jti: str) -> bool:
    redis = get_redis()
    try:
        return await redis.exists(BLACKLIST_KEY.format(jti)) == 1
    finally:
        await redis.aclose()


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> dict[str, str]:
    """Validate a refresh token, rotate it (blacklist the old jti), return a new pair."""
    payload = decode_token(refresh_token, expected_type="refresh")
    jti = str(payload["jti"])
    if await _is_blacklisted(jti):
        raise UnauthorizedError("Refresh token revoked")
    admin = await get_admin_by_id(session, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise UnauthorizedError("Admin no longer active")
    await _revoke_jti(jti, _jti_ttl_seconds(payload))
    return build_token_pair(admin)


async def logout(refresh_token: str) -> None:
    """Blacklist the refresh token's jti for its remaining lifetime."""
    payload = decode_token(refresh_token, expected_type="refresh")
    await _revoke_jti(str(payload["jti"]), _jti_ttl_seconds(payload))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_auth_service.py -v
```

Expected: PASS (7 tests). Requires Postgres + Redis running.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/services tests/unit/test_auth_service.py
git commit -m "feat: add admin auth service with refresh rotation and revocation"
```

---

### Task 4: Auth API — schemas, dependency, router

**Files:**
- Create: `backend/app/schemas/__init__.py` (empty), `backend/app/schemas/auth.py`, `backend/app/api/deps.py`, `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/integration/test_auth.py`

**Interfaces:**
- `app.schemas.auth`: `LoginRequest{username, password}`, `RefreshRequest{refresh_token}`, `LogoutRequest{refresh_token}`, `TokenPair{access_token, refresh_token, token_type="bearer"}`, `AdminOut{id, username, email, is_active}` (`from_attributes`), `LoginResponse(TokenPair){admin}`.
- `app.api.deps.get_current_admin` — FastAPI dependency: `HTTPBearer(auto_error=False)` → decode access token → load admin (must exist + active) → `Admin`, else `UnauthorizedError`. This is the hook Plan 3's `require_permission` will wrap.
- `app.api.v1.auth.router` — `POST /auth/login` (5/min), `POST /auth/refresh` (10/min), `POST /auth/logout` (10/min, 204), `GET /auth/me` (60/min).
- Every endpoint declares `request: Request` and `response: Response` (slowapi requirement, see Global Constraints).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_auth.py`:

```python
from httpx import AsyncClient

from app.core.security import hash_password
from app.models.rbac import Admin


async def _seed_admin(session, username="root", password="secret123") -> Admin:
    admin = Admin(
        username=username,
        email=f"{username}@netgrid.local",
        password_hash=hash_password(password),
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    return admin


async def test_login_success(client, session):
    await _seed_admin(session)
    resp = await client.post("/api/v1/auth/login", json={"username": "root", "password": "secret123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["admin"]["username"] == "root"


async def test_login_invalid_credentials(client, session):
    await _seed_admin(session)
    resp = await client.post("/api/v1/auth/login", json={"username": "root", "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_login_validation_error(client):
    resp = await client.post("/api/v1/auth/login", json={"username": ""})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_me_requires_token(client, session):
    await _seed_admin(session)
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_me_with_token(client, session):
    admin = await _seed_admin(session)
    login = await client.post("/api/v1/auth/login", json={"username": "root", "password": "secret123"})
    token = login.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == admin.id
    assert body["username"] == "root"


async def test_refresh_flow_rotates(client, session):
    await _seed_admin(session)
    login = await client.post("/api/v1/auth/login", json={"username": "root", "password": "secret123"})
    old_refresh = login.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new = resp.json()
    assert new["access_token"]
    assert new["refresh_token"] != old_refresh  # rotation
    # the rotated-away token must no longer work
    resp2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


async def test_logout_revokes_refresh(client, session):
    await _seed_admin(session)
    login = await client.post("/api/v1/auth/login", json={"username": "root", "password": "secret123"})
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 204
    resp2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401


async def test_refresh_rejects_access_token(client, session):
    await _seed_admin(session)
    login = await client.post("/api/v1/auth/login", json={"username": "root", "password": "secret123"})
    access_token = login.json()["access_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/integration/test_auth.py -v
```

Expected: FAIL — `404` on `/api/v1/auth/login` (router not wired yet).

- [ ] **Step 3: Implement**

Create empty `backend/app/schemas/__init__.py`.

Create `backend/app/schemas/auth.py`:

```python
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool


class LoginResponse(TokenPair):
    admin: AdminOut
```

Create `backend/app/api/deps.py`:

```python
"""Shared FastAPI dependencies for authenticated endpoints."""
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.exceptions import UnauthorizedError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.models.rbac import Admin
from app.services.auth import get_admin_by_id

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Admin:
    """Resolve the authenticated admin from the access token.

    Authentication only — Plan 3 wraps this with require_permission(...) for
    authorization.
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_token(credentials.credentials, expected_type=TOKEN_TYPE_ACCESS)
    admin = await get_admin_by_id(session, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise UnauthorizedError("Admin no longer active")
    return admin
```

Create `backend/app/api/v1/auth.py`:

```python
"""Auth endpoints: login, refresh, logout, me.

These four endpoints are the pre-RBAC exception to the "explicit permission
on every endpoint" rule — they are the authentication layer itself. Plan 3
(RBAC) adds permission checks to /auth/me and everywhere else.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.auth import (
    AdminOut,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
    pair = auth_service.build_token_pair(admin)
    return LoginResponse(admin=AdminOut.model_validate(admin), **pair)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(LIMITS["refresh"])
async def refresh(
    request: Request, response: Response, payload: RefreshRequest, session: SessionDep
) -> TokenPair:
    """POST /api/v1/auth/refresh — no permission required (auth endpoint)."""
    return TokenPair(**await auth_service.refresh_tokens(session, payload.refresh_token))


@router.post("/logout", status_code=204)
@limiter.limit(LIMITS["logout"])
async def logout(
    request: Request, response: Response, payload: LogoutRequest
) -> Response:
    """POST /api/v1/auth/logout — no permission required (auth endpoint)."""
    await auth_service.logout(payload.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=AdminOut)
@limiter.limit(LIMITS["me"])
async def me(
    request: Request,
    response: Response,
    admin: Annotated[Admin, Depends(get_current_admin)],
) -> AdminOut:
    """GET /api/v1/auth/me — requires a valid access token (auth-only until Plan 3)."""
    return AdminOut.model_validate(admin)
```

Modify `backend/app/api/v1/router.py` to:

```python
from fastapi import APIRouter

from .auth import router as auth_router
from .health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/integration/test_auth.py -v
```

Expected: PASS (8 tests). Requires Postgres + Redis running.

- [ ] **Step 5: Gates + commit**

```bash
ruff check app tests
ruff format --check app tests
mypy app
git add app/schemas app/api/deps.py app/api/v1/auth.py app/api/v1/router.py tests/integration/test_auth.py
git commit -m "feat: add admin auth API (login, refresh, logout, me)"
```

---

### Task 5: Full gates + CLAUDE.md sync

**Files:**
- Modify: `CLAUDE.md` (check Phase 2, fold auth decisions)

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

Expected: ruff clean, mypy clean, pytest green — 13 (Plan 1) + 9 + 3 + 7 + 8 = **40 tests** (2 of the 8 auth integration tests are the rate-limit tests already counted in the 3; recount from actual output — the point is the full suite is green).

> Note for the executing agent: the exact total is whatever `pytest -q` reports; the requirement is that every test in `tests/` passes, including the new `test_security.py`, `test_auth_service.py`, `test_auth.py`, and `test_rate_limit.py`.

- [ ] **Step 2: Update `CLAUDE.md`**

Apply exactly these changes:

1. In `Build Phases`, check off **Phase 2 — Admin auth (JWT)**: change `- [ ]` to `- [x]`.
2. In `Pinned decisions` (under Architecture), append one bullet:

```
- Admin auth: JWT access (15 min) + refresh (7 day) tokens with `sub`/`type`/`jti` claims (HS256); refresh tokens rotate and logout revokes via a Redis jti blacklist (`token:blacklist:<jti>`, TTL = remaining token life); login rate-limited 5/min/IP via slowapi, config centralized in `app/core/rate_limit.py`.
```

3. In `RBAC > Enforcement`, after the "No endpoint should be reachable by any authenticated admin by default" bullet, add:

```
- Exception: the Phase 2 `/api/v1/auth/*` endpoints (login/refresh/logout/me) are the authentication layer itself; Plan 3 adds `require_permission` to `/auth/me` and all future endpoints.
```

4. In `Rate Limiting > 1. FastAPI API rate limiting`, no change needed — the existing text (slowapi, 5/min/IP on login, centralized `app/core/rate_limit.py`) is exactly what this plan implements. Do **not** check off Phase 8 (it also covers tiered limits across all existing endpoints + window/per-IP test coverage at the API-wide scale).

- [ ] **Step 3: Final commit**

```bash
cd ..
git add CLAUDE.md
git commit -m "docs: check off Phase 2, pin JWT/rate-limit auth decisions in CLAUDE.md"
```

---

## Self-Review (to verify when implementing)

- **Spec coverage:** every Phase 2 deliverable from CLAUDE.md maps to a task — argon2 hashing (T1), login issuing access+refresh JWTs (T4), refresh + logout/revocation (T3, T4), auth rate limiting 5/min/IP (T2), full unit + integration coverage incl. token creation/validation, login flow, refresh, invalid credentials, lockout (T1–T4).
- **Placeholder scan:** no TBD/TODO; every code step carries full content. Conditional notes are limited to verified fallbacks (sleep 1.5s if the window test flakes; scan+delete if a future storage loses `reset()`).
- **Layering compliance:** routers (`api/v1/auth.py`) only parse/validate and call `app/services/auth.py`; all DB access is in the service; services import from `core` only, never from `api/`. `get_current_admin` delegates its DB lookup to `auth_service.get_admin_by_id` so even the dependency honors the rule.
- **Type consistency:** `create_app()` signature stays parameterless (Plan 1 contract); `decode_token` returns `dict[str, Any]` so `payload["sub"]`/`["jti"]`/`["exp"]` survive `mypy --strict` in services; `TokenPair`/`LoginResponse`/`AdminOut` names are used identically in schemas, router, and tests.
- **Verified upstream:** passlib 1.7.4 + argon2-cffi 25.1.0 hash/verify roundtrip passes on Python 3.14 (no pin needed). slowapi's `limit()` decorator binds its `Limiter` instance at decoration time — hence the module-level `limiter` + `limiter.reset()` test strategy (Redis storage supports reset under `key_prefix`) rather than swapping `app.state.limiter`. slowapi injects headers through the endpoint's `response` param — every limited endpoint declares `request: Request, response: Response`.
- **Out of scope by design (later plans):** RBAC/permission claims (Plan 3), tiered limits on non-auth routes + Redis-only rate-limit storage details (Phase 8), audit-log writes on login (Phase 13), frontend login screen (Phase 12), CI additions (none needed — the backend job already starts postgres + redis).
