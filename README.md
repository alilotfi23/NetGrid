# NetGrid

A modern ISP subscriber management and billing platform — subscriber accounts, plans,
billing, live sessions, NAS devices, and data-cap enforcement — with **real RADIUS AAA**
via FreeRADIUS and an admin web dashboard. Built from scratch (as a university capstone)
to match the functional scope of [IBSng](https://github.com/pouyadarabi/IBSng) — **not**
a port of its PHP/Smarty code.

**Stack:** FastAPI (async SQLAlchemy 2.0 + asyncpg) · Next.js (App Router + shadcn/ui) ·
PostgreSQL · FreeRADIUS (`rlm_sql_postgresql`) · Redis · Docker Compose

> Architecture decisions, pinned conventions, and the build-phase checklist live in
> [`CLAUDE.md`](./CLAUDE.md). This README is the human-facing overview + quickstart.

<!-- Fill in the GitHub owner/repo when the project gets a remote (git remote add origin …);
     the badge shows the CI workflow's check state on main. -->
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)

---

## What it does

- **Subscriber lifecycle** — CRUD with profile/billing metadata, statuses
  (`active` / `suspended` / `expired`), and credentials written straight into FreeRADIUS's
  `radcheck` table in the same transaction.
- **Plans → RADIUS groups** — bandwidth and quota mirror into `radgroupreply`
  (including the MikroTik 64-bit quota pair) the moment a plan is created or changed;
  assigning a subscriber to a plan writes `radusergroup`.
- **NAS device inventory** — shared secrets Fernet-encrypted at rest, mirrored 1:1 into
  FreeRADIUS's `nas` table; deactivating a device removes its row so FreeRADIUS rejects it.
- **Live sessions + CoA** — open `radacct` sessions with NAS/shortname joins, and RFC 5176
  Disconnect-Requests sent directly to the NAS via `pyrad` (the sim-nas container answers
  them with a real ACK, so the full disconnect loop is testable).
- **Billing** — monthly invoice generation (prorated, idempotent), payments, an overdue
  sweep, and a revenue report.
- **Data-cap lifecycle** — per-subscriber usage vs. quota (dashboard card + month-by-month
  history), an over-quota enforcement job that disconnects breaching sessions over CoA, and
  **per-GB overage surcharge billing** for usage beyond quota.
- **Admin auth + RBAC** — JWT access/refresh with rotation and revocation, argon2 password
  hashing, a `resource:action` permission model, and per-route `require_permission` checks.
- **Rate limiting** — slowapi/Redis tiers (strict on auth, moderate on writes, loose on reads).
- **Audit trail** — every meaningful action (create/update/delete, logins, disconnects,
  enforcement, billing runs) lands in `audit_log` and is browseable in the dashboard.
- **Frontend** — a full admin dashboard: KPI strip, revenue trend, live 30s-polling cards
  with stale indicators, recent-activity feed, and list/detail/new/edit pages for every
  resource.

## Architecture

```
Next.js + shadcn/ui  <-->  FastAPI (REST, /api/v1)  <-->  PostgreSQL  <-->  FreeRADIUS (sql module)
      (dashboard)        [RBAC + rate limit]            (shared DB)      (AAA on UDP 1812/1813)
                                  |
                                  v
                                Redis
                        (rate-limiter state, caches, token blacklist)
```

The key principle: **FastAPI and FreeRADIUS are separate processes that share one
PostgreSQL database.** There is no XML-RPC bridge, no custom RADIUS server, and no
subscriber-to-RADIUS sync/ETL layer — the app writes credentials, plan attributes, and NAS
rows *directly* into FreeRADIUS's standard schema tables in the same transactions as its
own tables (direct coupling). CoA/disconnect is a direct `pyrad` client call from FastAPI
to the NAS. `radacct` is owned by FreeRADIUS: the app only ever reads it.

## Repository layout

```
/backend         FastAPI app (app/api · services · models · schemas · core · jobs),
                 Alembic migrations, pytest suite (unit + integration + radius)
/frontend        Next.js dashboard (App Router) + Vitest/RTL tests
/freeradius      FreeRADIUS Docker image + raddb overrides (sql module, lockout policy)
/docker          Compose helpers: sim-nas container, MikroTik autorun script
/scripts         smoke_e2e.sh, seed_dev.py lives in backend/scripts
/docs            Design spec + implementation plans (docs/superpowers)
docker-compose.yml
.env.example     Every env var the app needs, with placeholders
CLAUDE.md        Architecture decisions, conventions, build phases
CONTRIBUTING.md  How to set up a dev environment, conventions, and PR process
```

## Prerequisites

- **Docker Desktop** (with Docker Compose v2) for the full stack
- **Python 3.12+** and **Node.js 20+** only if you develop on the host
- Free ports: `5432` (postgres), `6379` (redis), `8000` (backend), `3000` (frontend),
  `1812/1813` UDP (FreeRADIUS)

## Quickstart — full stack with Docker

```bash
# 1. Configure secrets (never commit .env)
cp .env.example .env        # at minimum set a strong JWT_SECRET and FERNET_KEY

# 2. Build and start every service
docker compose up -d --build
```

On first start, Postgres runs initdb scripts that create the FreeRADIUS schema
(`radacct`, `radcheck`, …) plus the hardening indexes and the `netgrid_test` database.
The NetGrid app tables are created by **Alembic automatically** — the backend container
runs `alembic upgrade head` (idempotent) before uvicorn starts, so a fresh
`docker compose up` is fully provisioned.

### Log in

The seed migration creates a bootstrap admin with the `super_admin` role:

- username: `superadmin` · password: `netgrid-admin` (**change it after first login**)

### Verify it's alive

```bash
# FastAPI health (no DB dependency — works even before migrations)
curl http://localhost:8000/api/v1/health          # -> {"status":"ok"}

# Dashboard
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000   # -> 200

# RADIUS -> DB round trip: unknown user must be rejected AND logged to radpostauth
docker compose exec freeradius radtest baduser badpass 127.0.0.1 0 testing123
docker compose exec postgres psql -U netgrid -d netgrid \
  -c "SELECT username, reply FROM radpostauth ORDER BY authdate DESC LIMIT 3;"
```

### Demo data + a simulated NAS

```bash
# Seed a realistic demo dataset (plans, NAS devices, subscribers, 12 months of
# invoices/payments, live sessions) — idempotent, safe to re-run.
cd backend && python scripts/seed_dev.py

# The sim-nas container sends periodic RADIUS Access-Requests to FreeRADIUS
# (auth path) and answers Disconnect/CoA-Requests on UDP 3799 with a real
# Disconnect-ACK (disconnect path). Register it and seed a subscriber:
bash scripts/setup-mikrotik-nas.sh        # or: python scripts/setup-mikrotik-nas.py
docker compose logs -f sim-nas            # watch Access-Accept / Access-Reject
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
| redis | `localhost:6379` | rate limiting, usage caches, refresh-token revocation |
| freeradius | `1812/1813` UDP | RADIUS auth/accounting against the shared DB |
| backend | `localhost:8000` | FastAPI under `/api/v1` |
| frontend | `localhost:3000` | Next.js dashboard |
| sim-nas | `3799/udp` | simulated NAS: periodic Access-Requests (auth-path testing) **and** an RFC 5176 CoA responder that ACKs Disconnect-Requests |

The compose network is pinned to `172.28.0.0/16` — FreeRADIUS `clients.conf` only accepts
packets from that subnet (`netgrid_radius_secret`) and from localhost (`testing123`, used
by `radtest` smoke checks). A real MikroTik RouterOS config is provided (requires a Linux
host with `/dev/net/tun`; see `docker/mikrotik/autorun.rsc`).

## API overview

All routes live under `/api/v1`, every error responds with
`{"error": {"code": "...", "message": "..."}}`, and list endpoints return paginated
`Page[T]` responses. Every endpoint requires an explicit RBAC permission.

| Area | Endpoints | Permission(s) |
|---|---|---|
| Auth | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` | auth layer (login rate-limited 5/min/IP) |
| Subscribers | `GET/POST /subscribers`, `GET/PATCH/DELETE /subscribers/{id}`, `GET /subscribers/stats`, `GET /subscribers/{id}/history`, `GET /subscribers/{id}/sessions`, `GET /subscribers/{id}/usage` | `subscribers:read/write/delete` |
| Plans | `GET/POST /plans`, `GET/PATCH /plans/{id}` | `plans:read/write` |
| NAS devices | `GET/POST /nas-devices`, `GET/PATCH/DELETE /nas-devices/{id}`, `POST /nas-devices/{id}/rotate-secret` | `nas_devices:read/write` |
| Sessions | `GET /sessions`, `POST /sessions/{id}/disconnect` | `sessions:read`, `sessions:disconnect` |
| Usage | `GET /usage` | `usage:read` |
| Invoices | `GET /invoices`, `GET /invoices/report`, `POST /invoices/generate`, `POST /invoices/overage/generate`, `GET /invoices/{id}`, `POST /invoices/{id}/payments` | `invoices:read/write` |
| Admins / roles | `GET/POST /admins`, `PATCH/DELETE /admins/{id}`, `PUT /admins/{id}/roles`, `GET/POST /roles`, `PATCH/DELETE /roles/{id}`, `PUT /roles/{id}/permissions`, `GET /permissions` | `admins:read/manage`, `roles:read/manage` |
| Audit log | `GET /audit-logs` | `audit_logs:read` |
| Health | `GET /health` | none |

## Background jobs (APScheduler)

| Job | Schedule | What it does |
|---|---|---|
| `monthly-invoice-generation` | 1st of month, 00:05 UTC | bills active subscribers on active plans (idempotent, prorated) |
| `daily-overdue-sweep` | daily, 00:10 UTC | flips issued invoices past due to `overdue` |
| `overage-billing` | 2nd of month, 00:15 UTC | bills per-GB surcharges for the previous month's over-quota usage |
| `quota-enforcement` | every 5 min (`quota_enforcement_interval_minutes`) | disconnects live sessions of subscribers at/over quota on enforcement-enabled plans (opt-in per plan, per-subscriber cooldown) |

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
there and adjust `DATABASE_URL` / `REDIS_URL` for host-side dev.

### Tests and quality gates

```bash
pytest -q                    # real Postgres (netgrid_test), never SQLite; needs pg+redis up
pytest -n auto               # pytest-xdist: per-worker DBs (netgrid_test_gw0, ...)
ruff check app tests         # lint
ruff format --check app tests
mypy app                     # strict mode
```

**388 backend tests** (unit + integration) and **306 frontend tests** (Vitest/RTL) pass at
HEAD. There is also a scripted RADIUS suite under `backend/tests/radius`
(`radtest`/`radclient` against a test FreeRADIUS instance, including the failed-auth
lockout policy).

## Development — frontend

```bash
cd frontend
npm install
npm run dev                  # http://localhost:3000
npm run typecheck && npm run lint && npx vitest run
```

## Migrations

- Apply: `cd backend && alembic upgrade head`
- Revert: `alembic downgrade base` (drops only NetGrid tables)
- Every schema change ships with an Alembic migration — never edit the schema by hand.
- The FreeRADIUS `rad*` tables are owned by Postgres initdb and are **never touched by
  Alembic**; don't rename or restructure them.

## CI

GitHub Actions runs on every push (`.github/workflows/ci.yml`):

- **backend** — `ruff` (lint + format), `mypy`, and `pytest -n auto` against a
  compose-provisioned Postgres (same initdb scripts as local dev)
- **frontend** — `typecheck` (`tsc --noEmit`), `eslint`, and the Vitest suite
- **smoke** — boots the API against migrated DBs and runs the self-cleaning smoke scripts
  (invoices, subscribers + plans, sessions)
- **radius** (separate, slower) — builds FreeRADIUS and smoke-checks the
  RADIUS → `rlm_sql` → Postgres path via `radtest`, plus the scripted lockout tests

The nightly workflow (`.github/workflows/nightly.yml`) runs the slow end-to-end checks:
the **full-stack e2e smoke** (`scripts/smoke_e2e.sh`), a **viewport regression audit**
(headless Chrome over every page at 375px and 1440px asserting no overflow, that
scrollable tables/charts pan inside their own cards, plus a dashboard pixel-diff baseline
persisted between nightlies), the RADIUS integration suite, and `next build`. Nightly
failures auto-open a `nightly-failure` GitHub issue that closes itself on the next green run.

## Docs

- `CLAUDE.md` — architecture, pinned decisions, RBAC/rate-limiting design, build phases
- `docs/` — design spec and task-by-task implementation plans
- `CONTRIBUTING.md` — setting up a dev environment, conventions, testing, and the PR process

## Status

**Feature-complete.** All 14 build phases are done — scaffolding, data model, admin auth
(JWT), RBAC, API conventions, subscribers, plans, NAS devices, rate limiting, sessions +
CoA, billing, FreeRADIUS abuse protection, the frontend dashboard, and CI — plus the
data-cap lifecycle milestone (usage aggregation, usage report + dashboard card,
per-subscriber usage history, over-quota enforcement, and overage surcharge billing).
See the **Build Phases** checklist in `CLAUDE.md` for the authoritative state.
