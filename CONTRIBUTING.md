# Contributing to NetGrid

Thanks for considering a contribution! NetGrid is a university capstone ISP subscriber
management and billing platform. This guide covers how to set up a development
environment, the conventions we follow, and how to get changes reviewed and merged.

## Code of conduct

Be respectful and constructive. This is a learning project — every reviewer was a
contributor once, and questions are welcome in issues and PRs.

## Development environment

### Prerequisites

- **Docker Desktop** with Compose v2 (postgres, redis, freeradius are provided by compose)
- **Python 3.12+**
- **Node.js 20+**
- Git

### One-time setup

```bash
# 1. Clone and enter the repo
git clone <your-fork-url> netgrid && cd netgrid

# 2. Backend venv + deps
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# 3. Frontend deps
cd ../frontend && npm install

# 4. Infrastructure (postgres + redis for dev and tests)
cd .. && docker compose up -d postgres redis

# 5. Backend env
cd backend
cp .env.example .env               # adjust DATABASE_URL / REDIS_URL if you changed ports
```

### Verify the setup

```bash
cd backend && alembic upgrade head && pytest -q          # tests run against netgrid_test
cd frontend && npm run typecheck && npx vitest run      # frontend checks
```

### Run the stack for manual testing

```bash
docker compose up -d --build        # full stack: postgres, redis, freeradius, backend, frontend
cd backend && python scripts/seed_dev.py   # realistic demo data (idempotent)
```

The bootstrap admin is `superadmin` / `netgrid-admin` (change it after first login).

## Branching and commit workflow

- Work on a branch off `main` named after the change, e.g. `feat/usage-history`,
  `fix/invoice-proration`.
- Keep changes small and focused; one logical unit per commit.
- **Commit messages follow Conventional Commits:**

  ```
  feat: add per-subscriber usage history endpoint
  fix: scope overdue sweep to kind='base' invoices
  docs: document the lockout policy in freeradius/README.md
  refactor: extract pagination helpers into app/core/pagination.py
  test: cover monthly_windows year-boundary rollover
  ```

  Explain *why* when the reason isn't obvious — the diff already shows *what*.

- **Commit early and often**, not one giant commit at the end. A feature commit includes
  its tests and migration in the same commit.
- Never commit `.env`, `node_modules`, `__pycache__`, `*.pyc`, or build artifacts —
  `.gitignore` already covers these; don't `git add -A` blindly.

## Project conventions (the short version)

The authoritative source is [`CLAUDE.md`](./CLAUDE.md) — read it before touching code.
The non-negotiables:

- **Layering**: routers are thin (parse/validate → call services); all DB access lives in
  services; services never import from `api/`.
- **API shape**: routes live under `/api/v1`; every error responds
  `{"error": {"code": "...", "message": "..."}}`; lists use `Page[T]`.
- **RBAC**: every new endpoint declares its required permission(s) explicitly via
  `require_permission("resource:action")` — never "any authenticated admin" by default,
  and never enforce RBAC only in the frontend.
- **Direct coupling to FreeRADIUS**: subscriber credentials → `radcheck`, plan attributes →
  `radgroupreply`, plan assignment → `radusergroup`, NAS devices → `nas`, all in the same
  transaction as our own tables. Do **not** add a sync/ETL layer, an XML-RPC bridge, or a
  custom RADIUS server.
- **Never rename or restructure** FreeRADIUS's standard `rad*` tables.
- **Migrations**: every model change ships with an Alembic migration in the same change
  set. Never edit the schema by hand.
- **No feature is done until it has tests** — unit + integration for every backend
  section, component tests for frontend components with real logic.

## Testing

Tests are mandatory per section. Backend tests run against a **real Postgres**
(`netgrid_test`), never SQLite; they need postgres + redis up (see setup above).

```bash
# Backend
cd backend
pytest -q                  # whole suite
pytest tests/unit/test_usage_service.py   # one file
pytest -n auto             # parallel (pytest-xdist, per-worker DBs)

# Quality gates — all must pass before a PR
ruff check app tests
ruff format --check app tests
mypy app                   # strict mode
```

```bash
# Frontend
cd frontend
npm run typecheck          # tsc --noEmit
npm run lint               # eslint
npx vitest run             # unit + component tests
```

For layout-affecting changes, also run the viewport audit (headless Chrome over every
page at 375px and 1440px, asserting no overflow and that tables/charts scroll inside
their cards):

```bash
cd frontend && node scripts/audit-viewports.mjs
```

For RADIUS changes, the scripted suite lives in `backend/tests/radius`
(`radtest`/`radclient` against a test FreeRADIUS instance, including the failed-auth
lockout policy) and runs as a separate, slower CI job.

## What needs tests

| Area | Unit tests | Integration tests |
|---|---|---|
| Auth / JWT | token creation/validation, password hashing | login flow, refresh, lockout |
| RBAC | permission resolution, caching | access denied/allowed per role, revocation |
| Rate limiting | limiter key/window logic | 429 at threshold, window reset, per-IP vs per-user |
| Subscribers | service-layer validation | CRUD via API + `radcheck` rows created/updated/deleted |
| Plans | plan → RADIUS group mapping | plan change reflected in `radgroupcheck`/`radgroupreply` |
| NAS devices | validation, secret handling | CRUD, uniqueness, secret never in responses |
| Billing | pricing/proration math | invoice generation, payment transitions, overage billing |
| Sessions / CoA | data transforms | live session read, disconnect triggers CoA |
| Jobs | job logic in isolation | scheduled job produces expected DB state |
| Usage | aggregation edge cases, windows | report + history endpoints, RBAC |

## Pull request process

1. **Open an issue first** for non-trivial changes (or pick an open one) so we agree on
   the approach before you write code.
2. Create a branch, implement, and push.
3. Open a PR against `main` with:
   - a short description of the change and *why*;
   - notes on anything reviewers should focus on;
   - confirmation that you ran the full quality gates above.
4. CI runs ruff, mypy, pytest, frontend typecheck/lint/tests, and the smoke suite.
   Fix anything it flags.
5. A maintainer reviews; address review comments with additional commits (no force-push).
6. Once approved, the PR is merged (squash) and the branch deleted.

## Reporting bugs / proposing features

- **Bugs**: include what you did, what you expected, what happened, and (if relevant)
  the backend or frontend logs. A failing test or a reproduction script is gold.
- **Features**: describe the problem you're solving, not just the solution. Check the
  open issues and `CLAUDE.md`'s build-phase checklist first — we deliberately keep scope
  tight, and some ideas conflict with pinned architecture decisions (e.g. no RPC bridge
  to FreeRADIUS, no Celery).

## Architecture decisions — don't change these without discussion

- FastAPI and FreeRADIUS share **one** PostgreSQL database (direct coupling, no sync layer)
- CoA/disconnect is a direct `pyrad` RFC 5176 call from FastAPI to the NAS
- Admin passwords: argon2 via passlib; JWT access (15 min) + rotating refresh (7 days)
  with Redis jti blacklist
- API rate limiting with slowapi/Redis, config centralized in `app/core/rate_limit.py`
- APScheduler for background jobs (no Celery unless a job needs a distributed queue)
- Frontend: Next.js App Router + shadcn/ui primitives + Tailwind only — no hand-rolled
  components where shadcn already provides one

If you think one of these should change, open an issue to discuss it **before** building
on top of a different approach.
