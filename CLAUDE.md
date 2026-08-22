# CLAUDE.md

This file gives Claude Code the context it needs to work in this repository. Read it fully before making changes. If a decision recorded here needs to change, update this file in the same commit as the code change — don't let it drift out of sync.

## Project Overview

**Name:** NetGrid
**Goal:** A modern ISP subscriber management and billing platform, inspired by IBSng (github.com/pouyadarabi/IBSng), rebuilt from scratch for a university capstone project.

This is **not** a port of IBSng's PHP/Smarty code. It is a fresh system with the same functional scope:
- Subscriber accounts, plans, and billing
- Real RADIUS AAA (Authentication, Authorization, Accounting) via **FreeRADIUS**, integrated through its `sql` module against our own database
- An admin web dashboard for staff to manage subscribers, plans, live sessions, invoices, and NAS devices
- Role-based access control (RBAC) for admin/staff users
- API rate limiting
- A real automated test suite covering every backend section

## Architecture

```
Next.js + shadcn/ui  <-->  FastAPI (REST API)  <-->  PostgreSQL  <-->  FreeRADIUS (sql module)
      (dashboard)         [RBAC + rate limit]        (shared DB)      (AAA on UDP 1812/1813)
                                  |
                                  v
                          Redis
                          - rate limiter state
                          - APScheduler/Celery job store (if used)
                          - short-lived caches (e.g. permission lookups)
```

Key principle: **FreeRADIUS and FastAPI are separate processes that share the same PostgreSQL database.** FastAPI never proxies RADIUS packets, and we do not build a custom RADIUS protocol server. Do not introduce an XML-RPC or custom RPC bridge between FastAPI and FreeRADIUS — that complexity is exactly what we are avoiding vs. IBSng.

### FreeRADIUS ↔ database coupling: decision

We use **direct coupling** (not a separate sync layer): FastAPI writes subscriber credentials and plan attributes straight into FreeRADIUS's standard schema tables (`radcheck`, `radgroupcheck`, `radgroupreply`, `radusergroup`). There is no intermediate `subscribers`-table-to-RADIUS sync job. A `plans` table in our own schema maps 1:1 to a RADIUS group; assigning a subscriber to a plan means writing a row into `radusergroup`. This is deliberately simple — do not introduce a sync/ETL layer between our tables and FreeRADIUS's tables unless this section is explicitly updated.

We do keep our own `subscribers` table (profile info, status, billing metadata) separate from `radcheck` — `radcheck` only holds what FreeRADIUS needs for auth (username + credential attribute). Join on username.

- Phase 5 implementation: subscriber credentials are written straight to `radcheck` in the same transaction as the `subscribers` row — one `Cleartext-Password` check per username (op `:=`), plus an `Auth-Type := Reject` check whenever the subscriber's status is not `active` (`active` | `suspended` | `expired`). Usernames are immutable after creation (renaming would rewrite radcheck rows). The `Cleartext-Password` storage is deliberate: FreeRADIUS needs a recoverable secret for PAP/MSCHAPv2 against NAS devices (the standard FreeRADIUS idiom), and the credential never touches the `subscribers` table. Note: although `schema.sql` declares `radcheck` columns as `UserName`/`Attribute`/`Value` (mixed case, unquoted), PostgreSQL folds them to lowercase — the effective schema (and the `RadCheck` model) is `id, username, attribute, op, value`.
- Phase 6 implementation: each plan maps 1:1 to a FreeRADIUS group (`plans.radius_group`); plan bandwidth/quota are mirrored into `radgroupreply` for that group in the same transaction as the plan row — `WISPr-Bandwidth-Max-Down`/`WISPr-Bandwidth-Max-Up` (kbps) and, when `quota_gb` is set, the Mikrotik 64-bit quota pair `Mikrotik-Total-Limit` (low 32 bits) + `Mikrotik-Total-Limit-Gigawords` (high 32 bits) — with stale check/reply rows replaced on change. (A 32-bit octet counter like `ChilliSpot-Max-Total-Octets` overflows above ~4 GiB, which is why quota uses the gigawords pair; verified live that FreeRADIUS returns both in Access-Accept.) `name` and `radius_group` are immutable after creation (rename = recreate). Assigning a subscriber to a plan writes one `radusergroup` row (`priority 1`); changing the plan replaces the row, clearing it removes it, and deleting the subscriber removes it — all in the same transaction as the `subscribers` change. There is no plan DELETE endpoint: decommissioning means `is_active=false` (subscribers keep their assignments). The same lowercase-identifier folding applies to `radusergroup`/`radgroupcheck`/`radgroupreply` (`username`/`groupname`/`attribute`/`op`/`value`).
- Phase 7 implementation: each `nas_devices` row (our inventory, source of truth) mirrors one FreeRADIUS `nas` row in the same transaction — `nasname` = `ip_address`, plus shortname/type/ports/server/community/description. The shared secret is Fernet-encrypted at rest in `nas_devices.secret_encrypted` (`FERNET_KEY`); the `nas` row carries the *plaintext* secret because FreeRADIUS must recover it for PAP/CHAP — the same idiom as radcheck's `Cleartext-Password` (the encrypted copy is for us, the plaintext is for FreeRADIUS). `ip_address` is immutable after creation (it is the RADIUS identity; rename = recreate). Deactivating a device removes its `nas` row, so FreeRADIUS treats it as an unknown NAS and rejects it; reactivating recreates the row (secret decrypted from storage). Secret rotation rewrites the `nas` row's secret; the dedicated `POST /nas-devices/{id}/rotate-secret` action (audit `rotate_secret`) rotates the secret in isolation, while a PATCH carrying `secret` rotates it alongside other field changes. Deleting the device removes both rows. The secret is never returned by the API.

### Identity domains — do not conflate

- **Admin users**: staff who log into the dashboard. JWT-based auth, governed by RBAC (see below).
- **Subscriber accounts**: end users authenticated by FreeRADIUS against routers/NAS devices (PAP/CHAP/MSCHAPv2). Never routed through the admin auth/RBAC stack.

### Pinned decisions

- API routes live under `/api/v1` and every error responds `{"error": {"code": "...", "message": "..."}}` (see `app/core/exceptions.py` + `app/core/errors.py`); success responses are plain data, lists use `Page[T]` (`app/core/pagination.py`).
- Layering: routers are thin (parse/validate → call services); all DB access lives in services; services never import from `api/`.
- NAS coupling is direct: `nas_devices` writes the FreeRADIUS `nas` table in the same transaction, with shared secrets Fernet-encrypted at rest (`FERNET_KEY`).
- CoA/session disconnect is sent directly from FastAPI with `pyrad` as an RFC 5176 Disconnect-Request — a client library call, not a bridge.
- Admin password hashing is pinned to `passlib` `CryptContext(schemes=["argon2"])`.
- Admin auth: JWT access (15 min) + refresh (7 day) tokens with `sub`/`type`/`jti` claims (HS256); refresh tokens rotate and logout revokes via a Redis jti blacklist (`token:blacklist:<jti>`, TTL = remaining token life); login rate-limited 5/min/IP via slowapi, config centralized in `app/core/rate_limit.py`.
- Tests run against real Postgres (dedicated `netgrid_test` database), never SQLite.
- Hardening indexes: unique `radcheck(username, attribute)`; `radacct(username)`, `radacct(acctstoptime)`, `radacct(framedipaddress)` (in `freeradius/raddb/mods-config/sql/main/postgresql/indexes.sql`).

## RBAC (Role-Based Access Control)

Applies to **admin users only** — subscriber auth is handled entirely by FreeRADIUS and is out of scope for RBAC.

### Model

- `admins` — staff accounts
- `roles` — named roles (e.g. `super_admin`, `billing_manager`, `network_operator`, `support_agent`, `auditor`)
- `permissions` — fine-grained, string-coded as `resource:action`, e.g.:
  - `subscribers:read`, `subscribers:write`, `subscribers:delete`
  - `plans:read`, `plans:write`
  - `invoices:read`, `invoices:write`
  - `nas_devices:read`, `nas_devices:write`
  - `sessions:read`, `sessions:disconnect` (CoA)
  - `usage:read` (view subscriber data-cap usage: current-month radacct consumption vs plan quota)
  - `admins:read` (list admins and their role assignments)
  - `admins:manage` (create/edit other admins and role assignments — restrict to `super_admin`)
  - `roles:read` (view roles and the permission catalog)
  - `roles:manage` (create/edit roles and assign permissions to them)
- `role_permissions` — many-to-many, roles → permissions
- `admin_roles` — many-to-many, admins → roles (support multiple roles per admin)

### Enforcement

- Implement as a FastAPI dependency, e.g. `require_permission("subscribers:write")`, applied per-route — never enforce RBAC only in the frontend.
- Resolve an admin's effective permission set at login, embed a permission-version or role hash in the JWT (or cache in Redis keyed by admin id), and invalidate/refresh on role change — don't require a DB hit on every request, but never let a revoked permission stay valid longer than a short cache TTL (e.g. 60s).
- Every new admin-facing endpoint must declare its required permission(s) explicitly. No endpoint should be reachable by "any authenticated admin" by default — require an explicit permission check.
- Exception: the Phase 2 `/api/v1/auth/*` endpoints (login/refresh/logout/me) are the authentication layer itself; Plan 3 adds `require_permission` to `/auth/me` and all future endpoints.
- Seed a default `super_admin` role with all permissions and a minimal `auditor` role with only `*:read` permissions as reference implementations; add others as features land.
- Write RBAC as its own module (`app/core/rbac.py` or `app/security/rbac.py`), not inlined per-router.
- Admin/role management endpoints (`/api/v1/admins`, `/api/v1/roles`, `/api/v1/permissions`) invalidate the affected admins' permission cache on every role/permission change (`invalidate_admin_permissions`), so revocation takes effect immediately, not just at the 60s TTL.
- Self-protection invariants enforced in `app/services/admins.py`: an admin cannot deactivate themselves, cannot change their own roles, and cannot edit a role they hold in a way that would strip their own `admins:manage` access — the classic lockout paths.

## Rate Limiting

Two separate concerns — do not conflate them:

1. **FastAPI API rate limiting** (admin dashboard + any public endpoints):
   - Use `slowapi` (Starlette/FastAPI-compatible, backed by Redis) for per-IP and per-admin-user limits.
   - Tiered limits: stricter on auth endpoints (e.g. login: 5/min/IP), moderate on writes, looser on reads.
   - Return standard `429 Too Many Requests` with a `Retry-After` header.
   - Rate limit config should be centralized (`app/core/rate_limit.py`), not scattered magic numbers per router.

2. **RADIUS-side abuse protection** (subscriber auth attempts):
   - This is a distinct problem from API rate limiting — handle it in FreeRADIUS policy, not in FastAPI.
   - Track failed auth attempts (e.g. via `radpostauth` logging or a small `unlang` policy) and lock out/slow down repeated failures per username or per NAS to mitigate brute-force credential attacks.
   - Document whatever approach is used under `/freeradius/README.md` when implemented.

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy 2.0 (async), Alembic for migrations, Pydantic v2
- **AAA layer:** FreeRADIUS configured with `rlm_sql` against PostgreSQL
- **Database:** PostgreSQL
- **Cache/rate-limit store:** Redis
- **Background jobs:** APScheduler (default) — only introduce Celery if a task genuinely needs a distributed queue
- **Frontend:** Next.js (App Router) + shadcn/ui + TanStack Query + TanStack Table + react-hook-form + zod + Recharts
- **Auth:** JWT (access + refresh) + passlib for admin password hashing; RBAC layer on top; FreeRADIUS handles subscriber credential checks directly against the DB
- **Testing:** pytest + pytest-asyncio + httpx `AsyncClient` (backend), Vitest + React Testing Library (frontend)
- **Deployment/dev:** Docker Compose (postgres, redis, freeradius, fastapi, frontend as services)

## Repository Structure (target)

```
/backend
  /app
    /api            # FastAPI routers, one module per resource
    /models          # SQLAlchemy models
    /schemas         # Pydantic schemas
    /services        # business logic (billing, provisioning, RBAC checks, etc.)
    /core            # config, security, db session, rbac.py, rate_limit.py
    /jobs            # APScheduler jobs
  /alembic
  /tests
    /unit            # one test module per app/services or app/core unit
    /integration      # API-level tests per router (auth, subscribers, plans, invoices, nas, sessions, rbac, rate_limit)
    /radius           # scripted radtest/radclient checks against a test FreeRADIUS instance
/freeradius
  /raddb             # FreeRADIUS config, sql module config, schema
  README.md          # abuse-protection policy notes once implemented
/scripts           # full-stack e2e smoke test (scripts/smoke_e2e.sh)
/frontend
  /app               # Next.js routes
  /components        # incl. shadcn components
  /lib
  /tests             # component/unit tests (Vitest + RTL)
/docker-compose.yml
/CLAUDE.md
```

## Core Data Model (starting point)

- `admins`, `roles`, `permissions`, `role_permissions`, `admin_roles`
- `subscribers` (profile/status/billing metadata — not credentials)
- `plans` (bandwidth/quota/price/duration; maps 1:1 to a RADIUS group)
- `nas_devices` (router inventory, shared secrets — mirrors FreeRADIUS `nas` table)
- `radcheck`, `radreply`, `radacct`, `radgroupcheck`, `radgroupreply`, `radusergroup` — **standard FreeRADIUS schema table/column names, do not rename**
- `invoices`, `payments`
- `audit_log` (admin_id, action, resource, resource_id, metadata jsonb, created_at)

When touching anything under `/freeradius`, preserve FreeRADIUS's expected table/column names exactly as documented in `raddb/mods-config/sql/main/postgresql/schema.sql`.

## Conventions

- Python: PEP 8, type-hint everything, async all the way through the FastAPI/SQLAlchemy stack (no blocking calls in route handlers)
- Commits: Conventional Commits style (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`)
- Migrations: every model change ships with an Alembic migration in the same change set — never edit the DB schema by hand
- Frontend: only use shadcn/ui primitives + Tailwind utility classes; don't hand-roll components that shadcn already provides
- Secrets (DB creds, RADIUS shared secrets, JWT keys) live in `.env`, never committed — use `.env.example` for documented placeholders
- Every new permission-gated endpoint documents its required permission string in its route docstring

## Testing — mandatory per section

**No feature is done until it has tests.** For every backend section/module, write both unit and integration coverage before considering it complete:

| Section | Unit tests | Integration tests |
|---|---|---|
| Auth (admin login/JWT) | token creation/validation, password hashing | login flow, refresh, invalid credentials, lockout |
| RBAC | permission resolution logic, role/permission caching | endpoint access denied/allowed per role, permission revocation takes effect |
| Rate limiting | limiter key/window logic | 429 triggered at threshold, resets after window, per-IP vs per-user isolation |
| Subscribers CRUD | service-layer validation | full CRUD via API, radcheck row created/updated/deleted correctly |
| Plans / RADIUS groups | plan→group mapping logic | plan change reflects in `radgroupcheck`/`radgroupreply` |
| NAS devices | validation, secret handling | CRUD via API, uniqueness constraints |
| Billing/invoices | pricing/proration logic | invoice generation job, payment status transitions |
| Sessions (radacct) | data transform/formatting | live session read, disconnect (CoA) triggers correctly |
| Background jobs | job logic in isolation (mock DB) | scheduled job runs and produces expected DB state |

- Backend: pytest + pytest-asyncio, httpx `AsyncClient` against the FastAPI app; `radtest`/`radclient` scripted checks for RADIUS auth verification against a test FreeRADIUS instance (Docker).
- Frontend: Vitest + React Testing Library for components with real logic (forms, tables with client-side sort/filter); skip trivial presentational components.
- Aim for meaningful coverage over percentage targets, but don't merge a new section with zero tests — treat "add tests" as part of the task, not a follow-up.
- CI (if/when set up): run the full backend test suite + linters on every push; RADIUS integration tests can run in a separate, slower job.

## Git Workflow — IMPORTANT

**Commit any changes you make.** After completing a task (a feature, fix, config change, or refactor), stage and commit it with a clear Conventional Commits message before moving to the next task. Do not batch unrelated changes into a single commit.

Specifically:
- Make small, logical commits as you go — not one giant commit at the end of a session
- A feature commit should include its tests in the same commit, not a separate later one
- Write commit messages that explain *why*, not just *what*, when the reason isn't obvious
- Never commit `.env`, `node_modules`, `__pycache__`, `*.pyc`, or other generated/secret files — check `.gitignore` covers these before the first commit
- If a change spans backend + frontend + freeradius config for one feature, that's fine as a single commit if it's genuinely one logical unit; split it if the pieces are independently meaningful
- Before committing, run relevant tests/linters; do not commit code with failing tests. If something is known-incomplete, say so in the message (e.g. `feat: add invoice model (migration pending)`)
- Do not force-push or rewrite shared history

## Build Phases — what to work on next

This is the build order. **Work top to bottom.** Do not start a phase until the phases it depends on are checked off, and do not skip ahead just because a later phase looks easier or more interesting. Each phase ends only when its code, migrations, and tests (per the Testing table above) are all committed — a phase is not "done" because the happy path works.

At the start of a session, scan this list top-down and resume at the first unchecked item. Check off an item in the same commit that completes it, so this file always reflects real state, not intent.

- [x] **Phase 0 — Repo & environment scaffolding**
  - Repository structure as laid out above (`/backend`, `/frontend`, `/freeradius`, `/alembic`, `/tests`)
  - `docker-compose.yml` wiring postgres, redis, freeradius, fastapi, frontend
  - `.env.example` with every variable the app will need (DB creds, Redis URL, JWT secret, RADIUS shared secret placeholder)
  - `.gitignore` covering `.env`, `node_modules`, `__pycache__`, `*.pyc`, build artifacts
  - Linter/formatter/type-checker config: `ruff`, `mypy` (backend); ESLint/Prettier (frontend) — pin the toolchain, don't leave it implicit
  - Empty FastAPI app boots, empty Next.js app boots, `docker compose up` brings up all services

- [x] **Phase 1 — Core data model & migrations**
  - SQLAlchemy models for `admins`, `roles`, `permissions`, `role_permissions`, `admin_roles`
  - SQLAlchemy models for `subscribers`, `plans`, `nas_devices`, `invoices`, `payments`
  - FreeRADIUS standard schema tables (`radcheck`, `radreply`, `radacct`, `radgroupcheck`, `radgroupreply`, `radusergroup`) created via the official FreeRADIUS `schema.sql`, not hand-modeled in SQLAlchemy unless the app needs to query them (if so, map read-only/exact-name)
  - `audit_log` table (admin_id, action, resource, resource_id, metadata, created_at) — see Prioritized Recommendations
  - Initial Alembic migration; verify `alembic upgrade head` / `downgrade` both work cleanly
  - Unit tests for model constraints (uniqueness, required fields)

- [x] **Phase 2 — Admin auth (JWT)**
  - Password hashing (pin the scheme — see Prioritized Recommendations, e.g. argon2)
  - Login endpoint issuing access + refresh JWTs
  - Refresh endpoint, logout/revocation strategy
  - Auth rate limiting (login: 5/min/IP, see Rate Limiting section)
  - Full unit + integration coverage per the Testing table (token creation/validation, login flow, refresh, invalid credentials, lockout)

- [x] **Phase 3 — RBAC**
  - `app/core/rbac.py` (or `security/rbac.py`) module: role/permission resolution, `require_permission(...)` dependency
  - JWT permission-version embedding or Redis-cached permission set, with the ≤60s revocation TTL
  - Seed `super_admin` (all permissions) and `auditor` (`*:read`) roles
  - Apply `require_permission` to every route from this point forward — no new endpoint after this phase should ship without an explicit permission check
  - Full unit + integration coverage (permission resolution, caching, access denied/allowed per role, revocation takes effect)
  - Admin/role CRUD endpoints (`/api/v1/admins`, `/api/v1/roles`, `/api/v1/permissions`) with cache invalidation on every role/permission change

- [x] **Phase 4 — API conventions layer**
  - Resolve the open "High" items from Prioritized Recommendations that affect every future endpoint: response/error envelope, `/api/v1/...` versioning, layering rules (router → service → session)
  - `app/core/exceptions.py` + FastAPI exception handlers implementing the pinned error shape
  - This phase exists so every resource built afterward is consistent — do not build Subscribers/Plans/etc. before this is settled

- [x] **Phase 5 — Subscribers CRUD + RADIUS credential coupling**
  - Subscribers API (RBAC-gated: `subscribers:read/write/delete`)
  - Service-layer logic writing/updating `radcheck` in the same transaction as `subscribers` (direct coupling — see architecture decision)
  - Full unit + integration coverage, including that `radcheck` rows are created/updated/deleted correctly alongside `subscribers`

- [x] **Phase 6 — Plans / RADIUS groups**
  - Plans API (RBAC-gated: `plans:read/write`)
  - Plan → RADIUS group mapping logic; assigning a subscriber to a plan writes `radusergroup`
  - Full unit + integration coverage, including that a plan change is reflected in `radgroupcheck`/`radgroupreply`

- [x] **Phase 7 — NAS devices**
  - NAS devices API (RBAC-gated: `nas_devices:read/write`), shared secrets Fernet-encrypted at rest (`FERNET_KEY`)
  - Each `nas_devices` row mirrors the FreeRADIUS `nas` table in the same transaction (direct coupling — see architecture decision); `ip_address` → `nasname`; deactivation removes the `nas` row
  - Alembic migration adding `ports`/`server`/`community` to `nas_devices` (the nas-table-mirrored columns)
  - Full unit + integration coverage (validation, secret handling, CRUD, uniqueness constraints, secret never in responses)

- [x] **Phase 8 — Rate limiting (API side)**
  - `slowapi` + Redis wiring, centralized in `app/core/rate_limit.py`
  - Tiered limits applied across existing endpoints (auth strict, writes moderate, reads loose)
  - Full unit + integration coverage (limiter logic, 429 at threshold, window reset, per-IP vs per-user isolation)

- [x] **Phase 9 — Sessions (radacct) & CoA**
  - Resolve the CoA/disconnect mechanism (open item in Prioritized Recommendations) before writing this phase's code — resolved: direct pyrad RFC 5176 Disconnect-Request from FastAPI to the NAS (see direct-coupling decision)
  - Live session read API (RBAC-gated: `sessions:read`)
  - Disconnect endpoint (RBAC-gated: `sessions:disconnect`) triggering RADIUS CoA
  - Full unit + integration coverage (data transform/formatting, live session read, disconnect triggers correctly)

- [x] **Phase 10 — Billing & invoices**
  - Pricing/proration logic, invoice generation, payment status transitions
  - Background job (APScheduler) for invoice generation
  - Full unit + integration coverage (pricing/proration logic, invoice generation job, payment status transitions, scheduled job produces expected DB state)

- [x] **Phase 11 — FreeRADIUS abuse protection**
  - Failed-auth tracking / lockout policy in FreeRADIUS (`radpostauth` or `unlang`), per the Rate Limiting section
  - Document the approach in `/freeradius/README.md`
  - `radtest`/`radclient` scripted checks under `/tests/radius`

- [x] **Phase 12 — Frontend dashboard**
  - Next.js + shadcn/ui screens for subscribers, plans, sessions, invoices, NAS devices, admin/role management — all landed (list/detail/new pages per resource, server-rendered pagination on invoices + audit logs, client-side sortable/searchable subscribers table, overdue-invoice alert banner, payments revenue report)
  - TanStack Query/Table wiring against the Phase 4 API conventions
  - Component tests (Vitest + RTL) for forms and client-side sort/filter tables

- [x] **Phase 13 — CI workflow**
  - GitHub Actions (`.github/workflows/ci.yml`): `pytest -n auto` (pytest-xdist, per-worker test DBs + Redis namespaces) + `ruff` (lint + format) + `mypy` on push, with the installed venv cached; frontend `typecheck`/`lint`/`test` on push with `next build` nightly (`.github/workflows/nightly.yml`); RADIUS integration tests as a separate slower job. Nightly also re-runs the RADIUS suite, and nightly failures open a GitHub issue (`nightly-failure` label) that closes itself on the next green run — see the `open/close-nightly-failure-issue` jobs
- [x] **Phase 13 (cont.) — hardening pass**
  - Revisit the remaining Medium/Low items in Prioritized Recommendations (audit log wiring if not already done, README.md, indexing pass on `radacct`) — all landed (audit log read API + viewer, README CI badge/section, `radacct` hardening indexes in the radius initdb scripts)
  - End-to-end smoke test across the full stack via `docker compose up` — `scripts/smoke_e2e.sh`, run nightly in `.github/workflows/nightly.yml` (it builds every image, so it stays off the push path); the backend container now runs `alembic upgrade head` on startup, so a fresh `docker compose up` is fully provisioned. Nightly also runs a viewport regression audit (`frontend/scripts/audit-viewports.mjs`) that seeds the demo dataset and asserts every page fits at 375px and 1440px in headless Chrome, that scrollable tables/charts scroll inside their cards without moving the page (scroll-position stability), and — via a dashboard pixel-diff baseline persisted as a CI artifact between nightly runs — that paint/layout drift fails the audit (failure screenshots uploaded as an artifact)

### Ongoing milestone — data-cap lifecycle (post-Phase-13)

- [x] **Usage aggregation service** — `app/services/usage.py`: current-month per-subscriber octet totals from `radacct` (attributed by session start), best-effort 60s Redis cache, worker-namespaced keys, `clear_usage_cache()`. 15 unit tests.
- [x] **Usage report API + dashboard card** — `GET /api/v1/usage` (RBAC `usage:read`, added via migration `a1b2c3d4e5f6`): per plan-assigned subscriber, consumed GB vs `quota_gb` with `pct_used`, plus rollup stats. Dashboard `Data cap usage` card (progress bars, over-quota flagging) polling on the shared 30s cadence.
- [x] **Per-subscriber usage history** — `GET /api/v1/subscribers/{id}/usage` (RBAC `subscribers:read`): month-by-month radacct consumption over the last N months (default 12, zero-filled gaps, attributed by session start) with `pct_used` against the current plan quota; rendered as a `Usage history` table (down/up/total + quota bar) on the subscriber profile page.
- [ ] **Over-quota enforcement job** (next) — APScheduler job polling the usage report and disconnecting breaching sessions via the existing pyrad CoA path, with `quota_enforced` audit events.

## Prioritized Recommendations (from architecture review)

These came out of a senior-level architecture/code audit of this file before implementation began. Treat the High items as decisions to resolve **before** writing the corresponding code, not cleanup to do afterward. When a recommendation below results in a decision, fold that decision into the relevant section above (e.g. Core Data Model, RBAC, Rate Limiting) and remove it from this table — this table is a working checklist, not a permanent home for the decision.

| Priority | Recommendation | Why it matters | Suggested implementation |
|---|---|---|---|
| Low | Name a linter/formatter/type-checker toolchain explicitly | "Run linters" is stated but nothing is named | `ruff` (lint + format) + `mypy --strict` on `app/` |

## What NOT to do

- Don't write a custom RADIUS protocol server — FreeRADIUS is the AAA layer, full stop, unless this file is explicitly updated to change that decision
- Don't introduce XML-RPC or any RPC bridge between FastAPI and FreeRADIUS
- Don't introduce a subscriber-to-RADIUS sync/ETL layer — we use direct coupling (see decision above)
- Don't add Celery/Redis-as-queue until there's a concrete job that needs it (Redis itself is already in use for rate limiting/caching)
- Don't rename or restructure FreeRADIUS's standard SQL schema tables
- Don't skip Alembic migrations for schema changes
- Don't enforce RBAC only in the frontend — every permission check must exist server-side
- Don't ship a new endpoint, service, or job without accompanying tests
