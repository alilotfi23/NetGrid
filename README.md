# NetGrid

A modern ISP subscriber management and billing platform — subscriber accounts, plans, billing,
live sessions, and NAS devices — with real RADIUS AAA via **FreeRADIUS** and an admin web
dashboard. Built from scratch for a university capstone project.

**Stack:** FastAPI (async SQLAlchemy 2.0 + asyncpg) · Next.js (App Router) · PostgreSQL ·
FreeRADIUS (`rlm_sql_postgresql`) · Redis · Docker Compose

> Architecture decisions, conventions, and build-phase tracking live in [`CLAUDE.md`](./CLAUDE.md).
> This README is the human onboarding quickstart.

<!-- Fill in the GitHub owner/repo when the project gets a remote (git remote add origin …);
     the badge shows the CI workflow's check state on main. -->
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)

---

## Repository layout

```
/backend        FastAPI app (app/), Alembic migrations, pytest suite
/frontend       Next.js dashboard (scaffold)
/freeradius     FreeRADIUS Docker image + raddb overrides
/docker         Postgres initdb helpers (test DB creation)
/docs           Design spec + implementation plans
docker-compose.yml
.env.example    Every env var the app needs, with placeholders
CLAUDE.md       Architecture decisions & build phases
```

## Prerequisites

- **Docker Desktop** (with Docker Compose v2) for the full stack
- **Python 3.12+** and **Node.js 20+** only if you develop on the host
- Free ports: `5432` (postgres), `6379` (redis), `8000` (backend), `3000` (frontend),
  `1812/1813` UDP (FreeRADIUS)

## Quickstart — full stack with Docker

```bash
# 1. Configure secrets (never commit .env)
cp .env.example .env        # at minimum set a strong JWT_SECRET

# 2. Build and start every service
docker compose up -d --build
```

On first start, Postgres runs the initdb scripts that create the FreeRADIUS schema
(`radacct`, `radcheck`, …), the hardening indexes, and the `netgrid_test` database. The
**NetGrid app tables are created by Alembic**, which must be run once from the host:

```bash
# 3. Create the NetGrid tables (admins, subscribers, plans, ...)
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash); Unix: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
```

### Verify it's alive

```bash
# FastAPI health (uses no DB — works even before migrations)
curl http://localhost:8000/api/v1/health          # -> {"status":"ok"}

# Dashboard
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000   # -> 200

# RADIUS -> DB round trip: unknown user must be rejected AND logged to radpostauth
docker compose exec freeradius radtest baduser badpass 127.0.0.1 0 testing123
docker compose exec postgres psql -U netgrid -d netgrid \
  -c "SELECT username, reply FROM radpostauth ORDER BY authdate DESC LIMIT 3;"
```

### Tear down

```bash
docker compose down          # keep the postgres volume
docker compose down -v       # also wipe the database
```

## Services

| Service | Address | Notes |
|---|---|---|
| postgres | `localhost:5432` | DBs `netgrid` + `netgrid_test`, user `netgrid`/`netgrid` |
| redis | `localhost:6379` | rate limiting + token revocation (auth phase) |
| freeradius | `1812/1813` UDP | RADIUS auth/accounting against the shared DB |
| backend | `localhost:8000` | FastAPI under `/api/v1`, hot-reloads |
| frontend | `localhost:3000` | Next.js |

The compose network is pinned to `172.28.0.0/16` — FreeRADIUS `clients.conf` only accepts
packets from that subnet (`netgrid_radius_secret`) and from localhost (`testing123`, used by
`radtest` smoke checks).

## Development — backend

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -e ".[dev]"

# Postgres + Redis for dev/tests
docker compose up -d postgres redis

# Migrations
alembic upgrade head

# Run the API on the host
uvicorn app.main:app --reload
```

Settings are read from `backend/.env` (or environment variables) — copy `.env.example`
there and adjust `DATABASE_URL`/`REDIS_URL` for host-side dev.

### Tests and quality gates

```bash
pytest -q                    # needs postgres + redis running; uses real Postgres (netgrid_test), never SQLite
ruff check app tests
ruff format --check app tests
mypy app                     # strict mode
```

## Development — frontend

```bash
cd frontend
npm install
npm run dev                  # http://localhost:3000
```

## Migrations

- Apply: `cd backend && alembic upgrade head`
- Revert: `alembic downgrade base` (drops only NetGrid tables)
- Every schema change ships with an Alembic migration — never edit the schema by hand.
- The FreeRADIUS `rad*` tables are owned by Postgres initdb and are **never touched by
  Alembic**; don't rename or restructure them.
- The `seed super admin` migration creates a dev bootstrap account with the
  `super_admin` role and all permissions — **change the password after first login**:
  `superadmin` / `netgrid-admin`.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push — see the status badge at the
[top of this README](#netgrid):

- **backend** — `ruff` (lint + format), `mypy`, and `pytest` against a compose-provisioned
  Postgres (same initdb scripts as local dev)
- **frontend** — `typecheck` (`tsc --noEmit`), `eslint`, the Vitest suite, and `next build`
- **smoke** — boots the API against migrated DBs and runs the self-cleaning smoke scripts
  (invoices, subscribers + plans, sessions)
- **radius** (separate, slower) — builds FreeRADIUS and smoke-checks the RADIUS → `rlm_sql` →
  Postgres path via `radtest`, plus the scripted lockout tests under `backend/tests/radius`

## Docs

- `CLAUDE.md` — architecture, pinned decisions, RBAC/rate-limiting design, build phases
- `docs/` — design spec and task-by-task implementation plans (`docs/superpowers/plans/`)

## Status

Foundation phase complete (repo scaffolding, data model + initial migration, API conventions
layer, FreeRADIUS + frontend containers, CI). Admin auth (JWT) is planned next — see the
**Build Phases** checklist in `CLAUDE.md` for the current state.
