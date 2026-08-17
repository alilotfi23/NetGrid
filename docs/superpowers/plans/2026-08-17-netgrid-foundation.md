# NetGrid Foundation Implementation Plan (Plan 1 of 5 — Days 0–1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the NetGrid repository skeleton, Docker services (postgres, redis, freeradius, fastapi, frontend), the full SQLAlchemy data model with its initial Alembic migration, and the API conventions layer (`/api/v1` + error envelope) — all verified by tests and smoke checks. This is the foundation every later plan (Auth+RBAC, Core Resources, Sessions+Billing+Hardening, Frontend+Polish) builds on.

**Architecture:** FastAPI (async SQLAlchemy 2.0 + asyncpg) and FreeRADIUS (alpine package, `rlm_sql_postgresql`) share one PostgreSQL database. Postgres initdb applies the official FreeRADIUS `schema.sql` (vendored from the exact alpine package version we run) plus NetGrid hardening indexes. A custom alpine FreeRADIUS image overrides only three raddb files (`clients.conf`, `mods-enabled/sql`, `sites-enabled/default`); everything else comes from the package defaults. The API exposes routes under `/api/v1` with a uniform `{"error": {"code", "message"}}` envelope.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, Pydantic v2 + pydantic-settings, ruff + mypy, pytest + pytest-asyncio + httpx; Docker Compose (postgres:16-alpine, redis:7-alpine, alpine FreeRADIUS 3.0.27, python:3.12-slim, node:20-alpine Next.js).

## Global Constraints

- Python >= 3.12; async all the way through the FastAPI/SQLAlchemy stack (no blocking calls in route handlers).
- All API routes under `/api/v1/...`; errors always `{"error": {"code": "...", "message": "..."}}`; success responses are plain data.
- Layering: routers are thin (parse/validate → call services); all DB access lives in services; services never import from `api/`.
- Real Postgres for tests (dedicated `netgrid_test` database) — never SQLite.
- FreeRADIUS standard schema table/column names preserved exactly; rad* tables come from the official `schema.sql`, never hand-modeled in SQLAlchemy.
- ruff (lint + format) and `mypy --strict` on `app/` must be clean before each commit.
- Secrets live in `.env` (never committed); `.env.example` documents placeholders.
- Conventional Commits; commit at the end of every task.
- Host is Windows with Git Bash (repo at `D:/NetGrid`); Docker Desktop must be running. Python venv activation: `source .venv/Scripts/activate`. Expect `LF will be replaced by CRLF` warnings from git — harmless.
- Do not run `docker compose up` (all services) until Task 10; earlier tasks start only the services they need.

## File Structure

```
/backend
  pyproject.toml            # deps, ruff, mypy, pytest config
  Dockerfile
  alembic.ini, alembic/     # migrations (Task 7)
  app/
    __init__.py
    main.py                 # create_app(), mounts /api/v1 + handlers
    core/
      __init__.py
      config.py             # pydantic-settings, get_settings()
      db.py                 # async engine/session, get_session()
      exceptions.py         # AppError hierarchy
      errors.py             # register_exception_handlers(app)
      pagination.py         # Page[T] generic
    api/
      __init__.py
      v1/
        __init__.py
        router.py           # api_router, aggregates v1 routes
        health.py           # GET /health
    models/
      __init__.py           # imports every model (registers metadata)
      base.py               # Base, TimestampMixin, naming convention
      rbac.py               # Admin, Role, Permission + association tables
      plan.py               # Plan
      subscriber.py         # Subscriber
      nas.py                # NasDevice
      billing.py            # Invoice, Payment
      audit.py              # AuditLog
  tests/
    conftest.py             # engine + session fixtures (real Postgres)
    unit/
      test_models.py        # constraint tests
      test_pagination.py
    integration/
      test_health.py
      test_error_envelope.py
/freeradius
  Dockerfile                # alpine + freeradius, freeradius-postgresql, freeradius-utils
  raddb/
    clients.conf            # override: localhost + netgrid network client
    mods-enabled/sql        # override: rlm_sql_postgresql config
    sites-enabled/default   # override: trimmed site with sql enabled
    mods-config/sql/main/postgresql/
      schema.sql            # vendored official FreeRADIUS schema (Task 3 extraction)
      indexes.sql           # NetGrid hardening indexes (Task 3)
/docker/postgres/30-create-test-db.sql
/frontend                   # create-next-app scaffold (Task 9) + Dockerfile
docker-compose.yml
.env.example
.gitignore
docs/                       # existing spec lives here
```

---

### Task 1: Repo skeleton — .gitignore, .env.example, directory layout

**Files:**
- Create: `.gitignore`, `.env.example`, `docker/postgres/30-create-test-db.sql`
- Create (empty placeholder dirs via `.gitkeep`): `freeradius/raddb/mods-config/sql/main/postgresql/.gitkeep`

**Interfaces:**
- Produces: the env contract — every variable later tasks and compose read: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `JWT_ACCESS_TTL_MINUTES`, `JWT_REFRESH_TTL_DAYS`, `FERNET_KEY`, `RADIUS_SHARED_SECRET`.

- [ ] **Step 1: Create `.gitignore`**

```gitignore
# env & secrets
.env
.env.*
!.env.example

# python
__pycache__/
*.pyc
.venv/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
build/
dist/

# node
node_modules/
.next/
out/
npm-debug.log*

# misc
.DS_Store
*.log
```

- [ ] **Step 2: Create `.env.example`**

```dotenv
# --- PostgreSQL ---
POSTGRES_USER=netgrid
POSTGRES_PASSWORD=netgrid
POSTGRES_DB=netgrid

# --- App (host-side dev defaults match docker-compose) ---
DATABASE_URL=postgresql+asyncpg://netgrid:netgrid@localhost:5432/netgrid
TEST_DATABASE_URL=postgresql+asyncpg://netgrid:netgrid@localhost:5432/netgrid_test
REDIS_URL=redis://localhost:6379/0

# --- JWT (Phase 2 - auth) ---
JWT_SECRET=change-me-generate-a-long-random-string
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=7

# --- Fernet key for NAS shared secrets at rest (Phase 7) ---
FERNET_KEY=

# --- RADIUS ---
RADIUS_SHARED_SECRET=netgrid_radius_secret
```

- [ ] **Step 3: Create `docker/postgres/30-create-test-db.sql`**

```sql
CREATE DATABASE netgrid_test OWNER netgrid;
```

- [ ] **Step 4: Verify**

Run: `git status --short`
Expected: `.gitignore`, `.env.example`, `docker/` and `freeradius/` placeholders untracked; no `docs/` or `CLAUDE.md` listed as modified.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .env.example docker/postgres/30-create-test-db.sql freeradius/raddb/mods-config/sql/main/postgresql/.gitkeep
git commit -m "chore: add repo skeleton, env template, and gitignore"
```

---

### Task 2: Backend scaffolding — pyproject.toml, app package, Dockerfile

**Files:**
- Create: `backend/pyproject.toml`, `backend/Dockerfile`, `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/api/__init__.py`, `backend/app/api/v1/__init__.py`, `backend/.dockerignore`

**Interfaces:**
- Produces: package name `netgrid-backend` with import root `app`; ruff/mypy/pytest config that all later tasks rely on (`mypy --strict` on `app/`, pytest `asyncio_mode = "auto"`).

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "netgrid-backend"
version = "0.1.0"
description = "NetGrid ISP subscriber management and billing API"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "redis>=5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.5",
    "mypy>=1.10",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
files = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> If `pip install .` fails with "No module named setuptools", add `RUN pip install --no-cache-dir setuptools` before the install line. (The official python:3.12-slim image bundles setuptools, so this should not trigger.)

- [ ] **Step 3: Create `backend/.dockerignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
```

- [ ] **Step 4: Create empty package markers**

`backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/api/__init__.py`, `backend/app/api/v1/__init__.py` — each an empty file.

- [ ] **Step 5: Install and verify toolchain**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev]"
ruff check app
ruff format --check app
mypy app
```

Expected: ruff and mypy exit 0 (the package has no code yet, so both trivially pass).

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "chore: scaffold FastAPI backend with ruff/mypy toolchain"
```

---

### Task 3: Database plumbing — vendor RADIUS schema, docker-compose (postgres + redis)

**Files:**
- Create: `docker-compose.yml`
- Create: `freeradius/raddb/mods-config/sql/main/postgresql/schema.sql` (extraction command below)
- Create: `freeradius/raddb/mods-config/sql/main/postgresql/indexes.sql`

**Interfaces:**
- Produces: services `postgres` (user `netgrid`/`netgrid`, db `netgrid`, initdb loads `10-radius-schema.sql` → `20-radius-indexes.sql` → `30-create-test-db.sql`, healthcheck `pg_isready`) and `redis` (healthcheck `redis-cli ping`); fixed compose network `netgrid` with subnet `172.28.0.0/16` (FreeRADIUS client entries and later services depend on this exact subnet).

- [ ] **Step 1: Vendor the official FreeRADIUS schema from the exact alpine package version we run**

```bash
mkdir -p freeradius/raddb/mods-config/sql/main/postgresql
docker run --rm --entrypoint sh alpine:3.20 -c "apk add --no-cache freeradius freeradius-postgresql >/dev/null 2>&1 && cat /etc/raddb/mods-config/sql/main/postgresql/schema.sql" > freeradius/raddb/mods-config/sql/main/postgresql/schema.sql
```

Expected: the file exists and contains `CREATE TABLE radacct`, `radcheck`, `radgroupcheck`, `radgroupreply`, `radreply`, `radusergroup`, `radpostauth`, and `nas` table definitions plus index creation.

- [ ] **Step 2: Create `freeradius/raddb/mods-config/sql/main/postgresql/indexes.sql`**

```sql
-- NetGrid hardening indexes. The official schema.sql above is left untouched;
-- these are additive. Requires the rad* tables to exist (runs after 10-radius-schema.sql).
CREATE UNIQUE INDEX IF NOT EXISTS uq_radcheck_username_attribute ON radcheck (username, attribute);
CREATE INDEX IF NOT EXISTS ix_radacct_username ON radacct (username);
CREATE INDEX IF NOT EXISTS ix_radacct_acctstoptime ON radacct (acctstoptime);
CREATE INDEX IF NOT EXISTS ix_radacct_framedipaddress ON radacct (framedipaddress);
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
name: netgrid

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: netgrid
      POSTGRES_PASSWORD: netgrid
      POSTGRES_DB: netgrid
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./freeradius/raddb/mods-config/sql/main/postgresql/schema.sql:/docker-entrypoint-initdb.d/10-radius-schema.sql:ro
      - ./freeradius/raddb/mods-config/sql/main/postgresql/indexes.sql:/docker-entrypoint-initdb.d/20-radius-indexes.sql:ro
      - ./docker/postgres/30-create-test-db.sql:/docker-entrypoint-initdb.d/30-create-test-db.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U netgrid -d netgrid"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [netgrid]

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [netgrid]

  freeradius:
    build: ./freeradius
    ports:
      - "1812:1812/udp"
      - "1813:1813/udp"
    depends_on:
      postgres:
        condition: service_healthy
    networks: [netgrid]

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://netgrid:netgrid@postgres:5432/netgrid
      REDIS_URL: redis://redis:6379/0
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/app/app
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks: [netgrid]

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    networks: [netgrid]

networks:
  netgrid:
    ipam:
      config:
        - subnet: 172.28.0.0/16

volumes:
  pgdata:
```

> The `freeradius`, `backend`, and `frontend` services reference Dockerfiles created in Tasks 8, 2, and 9. Do not run `docker compose up` (whole stack) until Task 10. The next step starts only `postgres` and `redis`.

- [ ] **Step 4: Start postgres and redis, verify schema load**

```bash
docker compose up -d postgres redis
docker compose exec postgres psql -U netgrid -d netgrid -c "\dt"
```

Expected: `\dt` lists `radacct`, `radcheck`, `radgroupcheck`, `radgroupreply`, `radreply`, `radusergroup`, `radpostauth`, `nas` (all owned by netgrid).

- [ ] **Step 5: Verify hardening indexes and test database**

```bash
docker compose exec postgres psql -U netgrid -d netgrid -c "\di radcheck*"
docker compose exec postgres psql -U netgrid -l
```

Expected: `uq_radcheck_username_attribute` index exists; `netgrid_test` database exists in the listing.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml freeradius/raddb/mods-config/sql/main/postgresql
git commit -m "chore: add docker-compose with postgres and redis, wire RADIUS schema init"
```

---

### Task 4: Core app — config, async DB session, health endpoint

**Files:**
- Create: `backend/app/core/config.py`, `backend/app/core/db.py`, `backend/app/main.py`, `backend/app/api/v1/router.py`, `backend/app/api/v1/health.py`
- Test: `backend/tests/integration/test_health.py`
- Create: `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py` (empty)

**Interfaces:**
- Produces:
  - `app.core.config.get_settings() -> Settings` — cached; fields: `app_name`, `debug`, `database_url`, `test_database_url`, `redis_url`, `jwt_secret`, `jwt_access_ttl_minutes`, `jwt_refresh_ttl_days`, `fernet_key`, `cors_origins`. Reads `.env` (host-side) or env vars (compose).
  - `app.core.db.get_session() -> AsyncIterator[AsyncSession]` — FastAPI dependency; lazily builds the engine from `get_settings().database_url`.
  - `app.main.app` — the ASGI app; `GET /api/v1/health` → `{"status": "ok"}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_health.py`:

```python
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend
source .venv/Scripts/activate
pytest tests/integration/test_health.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Implement**

Create `backend/app/core/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "NetGrid API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://netgrid:netgrid@localhost:5432/netgrid"
    test_database_url: str = "postgresql+asyncpg://netgrid:netgrid@localhost:5432/netgrid_test"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7

    fernet_key: str = ""

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `backend/app/core/db.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None) -> AsyncEngine:
    """Build the shared async engine and session factory. Idempotent-safe for tests."""
    global _engine, _session_factory
    _engine = create_async_engine(url or get_settings().database_url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
```

Create `backend/app/api/v1/health.py`:

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Create `backend/app/api/v1/router.py`:

```python
from fastapi import APIRouter

from .health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI

from .api.v1.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(title="NetGrid API", version="0.1.0")
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
```

Create empty `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/integration/test_health.py -v
```

Expected: PASS.

- [ ] **Step 5: Run lint/type gates**

```bash
ruff check app tests
ruff format app tests
mypy app
```

Expected: all clean. (`ruff format` may reformat; re-run `ruff check` after.)

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add app config, async DB session, and health endpoint"
```

---

### Task 5: API conventions — error envelope, exception handlers, pagination

**Files:**
- Create: `backend/app/core/exceptions.py`, `backend/app/core/errors.py`, `backend/app/core/pagination.py`
- Modify: `backend/app/main.py` (register handlers)
- Test: `backend/tests/integration/test_error_envelope.py`, `backend/tests/unit/test_pagination.py`

**Interfaces:**
- Produces (later plans and tasks rely on these exact names):
  - `AppError` hierarchy: `NotFoundError(code="NOT_FOUND", 404)`, `ConflictError("CONFLICT", 409)`, `BadRequestError("BAD_REQUEST", 400)`, `UnauthorizedError("UNAUTHORIZED", 401)`, `ForbiddenError("FORBIDDEN", 403)` — each `AppError(message: str | None = None)`.
  - `app.core.errors.register_exception_handlers(app: FastAPI) -> None` — installs handlers for `AppError`, `StarletteHTTPException`, `RequestValidationError` (422 + `details`), and unhandled `Exception` (500).
  - `app.core.pagination.Page[T]` — Pydantic generic `{items, total, page, page_size}`; `paginate_params` is added in a later plan, this task ships the shape.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_error_envelope.py`:

```python
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import register_exception_handlers
from app.main import app


async def test_unknown_route_returns_error_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"]


async def test_method_not_allowed_returns_error_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


async def test_validation_error_returns_error_envelope_with_details():
    class Payload(BaseModel):
        count: int

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.post("/api/v1/echo")
    async def echo(payload: Payload) -> dict:
        return {"count": payload.count}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/api/v1/echo", json={"count": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in body["error"]


async def test_domain_error_uses_app_error_contract():
    from app.core.exceptions import NotFoundError

    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/api/v1/missing")
    async def missing() -> None:
        raise NotFoundError("Subscriber 42 not found")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v1/missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Subscriber 42 not found"
```

Create `backend/tests/unit/test_pagination.py`:

```python
from app.core.pagination import Page


def test_page_shape():
    page = Page[int](items=[1, 2, 3], total=100, page=1, page_size=10)
    assert page.items == [1, 2, 3]
    assert page.total == 100
    assert page.page == 1
    assert page.page_size == 10


def test_page_requires_all_fields():
    try:
        Page[int](items=[1])
    except Exception:
        return
    raise AssertionError("Page should require total, page, page_size")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
source .venv/Scripts/activate
pytest tests/unit/test_pagination.py tests/integration/test_error_envelope.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.errors'` / `'app.core.pagination'`.

- [ ] **Step 3: Implement**

Create `backend/app/core/exceptions.py`:

```python
class AppError(Exception):
    """Base for all domain errors. Every error surfaces as {"error": {code, message}}."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "Internal server error"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404
    message = "Resource not found"


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409
    message = "Resource already exists or is in conflict"


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    status_code = 400
    message = "Bad request"


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = 401
    message = "Authentication required"


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403
    message = "Insufficient permissions"
```

Create `backend/app/core/errors.py`:

```python
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exceptions import AppError

logger = logging.getLogger(__name__)

_STATUS_CODE_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
}


def _error_body(code: str, message: str, details: object | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODE_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_error_body(code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", "Request validation failed", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "Internal server error"),
        )
```

Create `backend/app/core/pagination.py`:

```python
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Uniform list response shape: {items, total, page, page_size}."""

    items: list[T]
    total: int
    page: int
    page_size: int
```

Modify `backend/app/main.py` to:

```python
from fastapi import FastAPI

from .api.v1.router import api_router
from .core.errors import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="NetGrid API", version="0.1.0")
    app.include_router(api_router, prefix="/api/v1")
    register_exception_handlers(app)
    return app


app = create_app()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/unit/test_pagination.py tests/integration/test_error_envelope.py -v
```

Expected: PASS (5 tests).

- [ ] **Step 5: Run lint/type gates**

```bash
ruff check app tests
ruff format app tests
mypy app
```

Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core backend/app/main.py backend/tests
git commit -m "feat: add API error envelope and pagination conventions"
```

---

### Task 6: SQLAlchemy models — full core data model

**Files:**
- Create: `backend/app/models/base.py`, `rbac.py`, `plan.py`, `subscriber.py`, `nas.py`, `billing.py`, `audit.py`, `__init__.py`
- Test: `backend/tests/unit/test_models.py`

**Interfaces:**
- Produces (all later plans consume these):
  - `app.models.base.Base` — DeclarativeBase with naming convention; `TimestampMixin` (`created_at`, `updated_at`, server defaults, `onupdate`).
  - Tables: `admins`, `roles`, `permissions`, `admin_roles`, `role_permissions`, `subscribers`, `plans`, `nas_devices`, `invoices`, `payments`, `audit_log`.
  - Model classes: `Admin(username, email, password_hash, is_active, roles)`, `Role(name, description, admins, permissions)`, `Permission(code, description, roles)`, `Subscriber(username, full_name, email, phone, status, plan_id, notes, plan)`, `Plan(name, radius_group, price, duration_days, bandwidth_down_mbps, bandwidth_up_mbps, quota_gb, description, is_active, subscribers)`, `NasDevice(name, ip_address, shortname, nas_type, secret_encrypted, description, is_active)`, `Invoice(subscriber_id, plan_name, period_start, period_end, amount, status, issued_at, due_at, paid_at, payments)`, `Payment(invoice_id, amount, method, reference, status, created_at, invoice)`, `AuditLog(admin_id, action, resource, resource_id, metadata_, created_at)`.
  - Uniqueness: `admins.username`, `admins.email`, `roles.name`, `permissions.code`, `subscribers.username`, `plans.name`, `plans.radius_group`, `nas_devices.name`, `nas_devices.ip_address`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_models.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
source .venv/Scripts/activate
pytest tests/unit/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'` (and `conftest.py` will fail on `app.models.base`).

- [ ] **Step 3: Create `backend/tests/conftest.py`**

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.base import Base
import app.models  # noqa: F401  # register every model on Base.metadata


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(get_settings().test_database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
```

- [ ] **Step 4: Implement the models**

Create `backend/app/models/base.py`:

```python
from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

Create `backend/app/models/rbac.py`:

```python
from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

admin_roles = Table(
    "admin_roles",
    Base.metadata,
    Column("admin_id", ForeignKey("admins.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    roles: Mapped[list["Role"]] = relationship(secondary=admin_roles, back_populates="admins")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    admins: Mapped[list[Admin]] = relationship(secondary=admin_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")
```

Create `backend/app/models/plan.py`:

```python
from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    radius_group: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    bandwidth_down_mbps: Mapped[int] = mapped_column(Integer, nullable=False)
    bandwidth_up_mbps: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_gb: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    subscribers: Mapped[list["Subscriber"]] = relationship(back_populates="plan")
```

Create `backend/app/models/subscriber.py`:

```python
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .plan import Plan


class Subscriber(TimestampMixin, Base):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)

    plan: Mapped["Plan | None"] = relationship(back_populates="subscribers")
```

> The `Mapped["Plan | None"]` forward reference resolves through SQLAlchemy's class registry at mapper configuration time. If the test run reports a `NameError` for `Plan`, add `from .plan import Plan` inside the existing `TYPE_CHECKING` block — the registry fallback makes this unnecessary, but the import is harmless if needed.

Create `backend/app/models/nas.py`:

```python
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class NasDevice(TimestampMixin, Base):
    __tablename__ = "nas_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    shortname: Mapped[str] = mapped_column(String(64), nullable=False)
    nas_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

Create `backend/app/models/billing.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False
    )
    plan_name: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="issued", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    due_at: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)

    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
```

Create `backend/app/models/audit.py`:

```python
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
```

Create `backend/app/models/__init__.py`:

```python
from .audit import AuditLog
from .base import Base
from .billing import Invoice, Payment
from .nas import NasDevice
from .plan import Plan
from .rbac import Admin, Permission, Role, admin_roles, role_permissions
from .subscriber import Subscriber

__all__ = [
    "Admin",
    "AuditLog",
    "Base",
    "Invoice",
    "NasDevice",
    "Payment",
    "Permission",
    "Plan",
    "Role",
    "Subscriber",
    "admin_roles",
    "role_permissions",
]
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/unit/test_models.py -v
```

Expected: PASS (6 tests). Requires the postgres container from Task 3 to be running.

- [ ] **Step 6: Run lint/type gates**

```bash
ruff check app tests
ruff format app tests
mypy app
```

Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models backend/tests/conftest.py backend/tests/unit/test_models.py
git commit -m "feat: add SQLAlchemy models for the core domain"
```

---

### Task 7: Alembic — initial migration, verify upgrade and downgrade

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/` (generated), `backend/alembic/versions/<hash>_initial_schema.py` (generated)
- Modify: `backend/alembic/env.py` (full content below)

**Interfaces:**
- Produces: `alembic upgrade head` / `alembic downgrade base` run cleanly against the dev DB; migration creates only NetGrid tables (rad* tables are owned by initdb, never touched by Alembic).

- [ ] **Step 1: Initialize Alembic**

```bash
cd backend
source .venv/Scripts/activate
alembic init alembic
```

- [ ] **Step 2: Rewrite `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models.base import Base
import app.models  # noqa: F401  # register every model on Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

> `alembic.ini` already contains `prepend_sys_path = .`, which puts `backend/` on `sys.path` so `from app...` imports resolve. Leave `sqlalchemy.url` in `alembic.ini` as the default placeholder — `env.py` overrides it.

- [ ] **Step 3: Generate the initial migration**

```bash
alembic revision --autogenerate -m "initial schema"
```

Expected: one new file `backend/alembic/versions/<hash>_initial_schema.py` containing `op.create_table` for all 11 tables plus indexes. Inspect it — if autogenerate also emitted statements about rad* tables (it should not, since they are not in metadata), delete those statements.

- [ ] **Step 4: Verify upgrade then downgrade then upgrade**

```bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Expected: all three commands succeed; `alembic current` reports `head`; after `downgrade base`, `psql \dt` still shows the rad* tables (Alembic must never touch them).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic
git commit -m "chore: add initial Alembic migration"
```

---

### Task 8: FreeRADIUS container — alpine image with SQL backend

**Files:**
- Create: `freeradius/Dockerfile`, `freeradius/raddb/clients.conf`, `freeradius/raddb/mods-enabled/sql`, `freeradius/raddb/sites-enabled/default`

**Interfaces:**
- Produces: compose service `freeradius` on UDP 1812/1813; reads/writes rad* tables in postgres as `netgrid`; accepts requests from `172.28.0.0/16` with shared secret `netgrid_radius_secret` and from `127.0.0.1` with `testing123` (used by in-container radtest smoke checks).

- [ ] **Step 1: Create `freeradius/Dockerfile`**

```dockerfile
FROM alpine:3.20

RUN apk add --no-cache freeradius freeradius-postgresql freeradius-utils

COPY raddb/clients.conf /etc/raddb/clients.conf
COPY raddb/mods-enabled/sql /etc/raddb/mods-enabled/sql
COPY raddb/sites-enabled/default /etc/raddb/sites-enabled/default

EXPOSE 1812/udp 1813/udp

CMD ["radiusd", "-f", "-X"]
```

- [ ] **Step 2: Create `freeradius/raddb/clients.conf`**

```
client localhost {
	ipaddr = 127.0.0.1
	secret = testing123
	require_message_authenticator = no
	nas_type = other
}

client netgrid_network {
	ipaddr = 172.28.0.0/16
	secret = netgrid_radius_secret
	require_message_authenticator = no
	nas_type = other
}
```

- [ ] **Step 3: Create `freeradius/raddb/mods-enabled/sql`**

```
sql {
	driver = "rlm_sql_postgresql"
	dialect = "postgresql"

	server = "postgres"
	port = 5432
	login = "netgrid"
	password = "netgrid"
	radius_db = "netgrid"

	acct_table1 = "radacct"
	acct_table2 = "radacct"
	postauth_table = "radpostauth"
	authcheck_table = "radcheck"
	authreply_table = "radreply"
	groupcheck_table = "radgroupcheck"
	groupreply_table = "radgroupreply"
	usergroup_table = "radusergroup"

	delete_stale_sessions = yes

	pool {
		start = 5
		min = 3
		max = 10
		spare = 3
		uses = 0
		retry_delay = 30
		lifetime = 0
		idle_timeout = 60
	}

	read_clients = yes
	client_table = "nas"

	read_groups = yes
	read_profiles = yes

	sqltrace = no

	$INCLUDE mods-config/sql/main/${dialect}/queries.conf
}
```

- [ ] **Step 4: Create `freeradius/raddb/sites-enabled/default`**

```
server default {
	listen {
		type = auth
		ipaddr = *
		port = 0
		limit {
			max_connections = 16
			lifetime = 0
			idle_timeout = 30
		}
	}

	listen {
		type = acct
		ipaddr = *
		port = 0
		limit {
			max_connections = 16
			lifetime = 0
			idle_timeout = 30
		}
	}

	authorize {
		preprocess
		chap
		mschap
		sql
		pap
	}

	authenticate {
		Auth-Type PAP {
			pap
		}
		Auth-Type CHAP {
			chap
		}
		Auth-Type MS-CHAP {
			mschap
		}
	}

	preacct {
		preprocess
		acct_unique
	}

	accounting {
		detail
		sql
	}

	session {
		sql
	}

	post-auth {
		sql
		Post-Auth-Type REJECT {
			sql
		}
	}
}
```

- [ ] **Step 5: Build and start, run config check**

```bash
docker compose build freeradius
docker compose up -d freeradius
docker compose exec freeradius radiusd -C
```

Expected: config check prints `Configuration appears to be OK`.

> If `radiusd -C` reports `Failed to find module "<name>"`, that module is not enabled in the alpine package's `mods-enabled`. Enable it by adding a line to the Dockerfile: `COPY raddb/mods-enabled/<name> /etc/raddb/mods-enabled/<name>` after copying a minimal module config from the package (`docker compose exec freeradius cat /etc/raddb/mods-available/<name>`), then rebuild. The modules referenced here (`preprocess`, `chap`, `mschap`, `pap`, `acct_unique`, `detail`) ship enabled in the alpine package, so this should not trigger.

- [ ] **Step 6: Smoke — RADIUS reaches the DB**

```bash
docker compose exec freeradius radtest baduser badpass 127.0.0.1 0 testing123
docker compose exec postgres psql -U netgrid -d netgrid -c "SELECT username, reply, authdate FROM radpostauth ORDER BY authdate DESC LIMIT 3;"
```

Expected: radtest prints `Access-Reject` (exit code may be non-zero — that is correct for a reject). The radpostauth query shows one row: `baduser` / `Access-Reject`. The row proves the full path: RADIUS packet → rlm_sql → postgres → write back.

- [ ] **Step 7: Commit**

```bash
git add freeradius
git commit -m "chore: add FreeRADIUS container with SQL backend"
```

---

### Task 9: Frontend scaffold — empty Next.js app boots

**Files:**
- Create: `frontend/` (create-next-app), `frontend/Dockerfile`, `frontend/.dockerignore`

**Interfaces:**
- Produces: compose service `frontend` on port 3000. Real screens arrive in the Frontend+Polish plan; this task only proves the app builds and serves.

- [ ] **Step 1: Scaffold**

```bash
cd frontend 2>/dev/null || mkdir -p frontend && cd frontend
npx --yes create-next-app@latest . --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm --turbopack
```

Expected: scaffold completes non-interactively; `npm run build` succeeds.

- [ ] **Step 2: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
```

- [ ] **Step 3: Create `frontend/.dockerignore`**

```
node_modules/
.next/
out/
npm-debug.log*
```

- [ ] **Step 4: Verify the container builds and serves**

```bash
docker compose build frontend
docker compose up -d frontend
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
```

Expected: `200`.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "chore: scaffold Next.js frontend"
```

---

### Task 10: Full-stack smoke + gates + CLAUDE.md sync

**Files:**
- Modify: `CLAUDE.md` (name + folded decisions, see Step 3)

**Goal:** Prove the whole stack boots together, all test/lint/type gates pass, and CLAUDE.md reflects the pinned decisions.

- [ ] **Step 1: Bring up the full stack**

```bash
docker compose up -d --build
docker compose ps
```

Expected: all five services `running` (or `healthy` for postgres/redis).

- [ ] **Step 2: Smoke every layer**

```bash
curl -s http://localhost:8000/api/v1/health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
docker compose exec freeradius radtest baduser badpass 127.0.0.1 0 testing123
docker compose exec postgres psql -U netgrid -d netgrid -c "SELECT username, reply FROM radpostauth ORDER BY authdate DESC LIMIT 3;"
```

Expected: `{"status":"ok"}`; `200`; `Access-Reject`; a radpostauth row for `baduser`. Also verify the backend log shows no errors: `docker compose logs backend | tail -20`.

- [ ] **Step 3: Update `CLAUDE.md`**

Apply exactly these changes:

1. Project name: replace `(TODO: pick a project name, e.g. "NetGrid")` with `NetGrid`.
2. In `Core Data Model`, add: "`audit_log` (admin_id, action, resource, resource_id, metadata jsonb, created_at)".
3. Add a short "Pinned decisions" subsection under Architecture or Core Data Model stating: API routes under `/api/v1` with `{"error": {"code", "message"}}` envelope; layering rules router → service → session (routers never call `session.execute`; services never import from `api/`); NAS coupling is direct (`nas_devices` ↔ `nas` in one transaction) with Fernet-encrypted secrets at rest; CoA/disconnect via pyrad RFC 5176 Disconnect-Request; password hashing pinned to `passlib` `CryptContext(schemes=["argon2"])`; test DB is real Postgres (dedicated `netgrid_test` database); hardening indexes on `radcheck(username, attribute)` unique and `radacct(username/acctstoptime/framedipaddress)`.
4. In `Prioritized Recommendations`, delete the rows that are now decisions: "Define the FastAPI internal layering contract", "Pin an API response/error envelope and versioning convention", "Decide the `nas_devices` ↔ `nas` sync strategy", "Decide and document the CoA/session-disconnect mechanism", "Require encryption at rest for `nas_devices` shared secrets", "Pin the password hashing scheme explicitly", "Specify test DB as real Postgres", "Add indexing guidance for `radacct`". Keep the rows still pending (audit log wiring as Medium is now resolved by the model — delete it too; keep CI, README, toolchain rows).
5. Check off **Phase 0**, **Phase 1**, and **Phase 4** boxes in `Build Phases` (completed by this plan: scaffolding, data model + migration, conventions layer). Leave all other phases unchecked.

- [ ] **Step 4: Run every gate from `backend/`**

```bash
cd backend
source .venv/Scripts/activate
ruff check app tests
ruff format --check app tests
mypy app
pytest -q
```

Expected: ruff clean, mypy clean, `pytest` green (11 tests: 6 models, 1 health, 4 envelope/pagination).

- [ ] **Step 5: Final commit**

```bash
cd ..
git add CLAUDE.md
git commit -m "docs: pin NetGrid decisions in CLAUDE.md, close out foundation phases"
```

---

## Self-Review (completed)

- **Spec coverage:** every Foundation-scope item from the spec maps to a task — scaffolding (T1, T2, T3, T9), docker-compose (T3), `.env.example`/`.gitignore` (T1), ruff/mypy (T2), models + `audit_log` + constraints (T6), FreeRADIUS `schema.sql` + hardening indexes (T3, T8), initial Alembic migration with clean upgrade/downgrade (T7), conventions layer with envelope + versioning + pagination (T4, T5), real-Postgres test DB (T3, T6), full-stack smoke (T10), CLAUDE.md sync (T10). Not in this plan by design: auth, RBAC, rate limiting, resource CRUD, CoA, billing, abuse policy, dashboard screens, CI — those are Plans 2–5.
- **Placeholder scan:** no TBD/TODO; every code step carries full content; the only conditional instructions (setuptools note, module-enable note, TYPE_CHECKING note) are explicit fallbacks with exact commands.
- **Type consistency:** `get_settings()`, `get_session()`, `Base`/`TimestampMixin`, `AppError` subclasses, `register_exception_handlers`, `Page[T]`, and all model field names are defined once here and referenced identically in later plans. `metadata_` is the JSONB field name on `AuditLog` (avoids shadowing `metadata`).
