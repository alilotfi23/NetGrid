# NetGrid — Design Spec

**Date:** 2026-08-17
**Status:** Approved (brainstorming session)
**Build window:** 5 days, live-demo capstone
**Project name:** NetGrid

## 1. Vision

NetGrid is a modern ISP subscriber management and billing platform, inspired by
IBSng, rebuilt from scratch as a university capstone. It is **not** a port of
IBSng's PHP/Smarty code — it is a fresh system with the same functional scope:

- Subscriber accounts, plans, and billing
- Real RADIUS AAA via **FreeRADIUS**, integrated through its `sql` module against our own database
- An admin web dashboard for staff to manage subscribers, plans, live sessions, invoices, and NAS devices
- Role-based access control (RBAC) for admin/staff users
- API rate limiting
- An automated test suite covering every backend section

## 2. The Demo (north star)

The 5-day build is judged by a **live demo**. This narrative is the target:

1. Admin logs into the NetGrid dashboard.
2. Admin creates a subscriber (username + password) and assigns a plan.
3. Credentials land in FreeRADIUS's `radcheck`; the plan maps to a RADIUS group
   (`radusergroup` + `radgroupcheck`/`radgroupreply`) — all in the same transaction.
4. A simulated login fires (`radtest`/`radclient`, or optionally the admin's real
   router/NAS pointed at our FreeRADIUS) — **Access-Accept** comes back.
5. The live session appears in the dashboard (read from `radacct`).
6. Invoice generation produces a bill for the subscriber's plan.
7. Stretch: CoA disconnect kills the session from the dashboard.

Everything in the demo is real — no stubs for the RADIUS path.

## 3. Scope

### In scope — full feature set

Everything in CLAUDE.md is in scope. Nothing is designed out; the *order* is what
protects the demo (see Build Order).

- Phase 0: repo scaffolding, docker-compose (postgres, redis, freeradius, fastapi, frontend),
  `.env.example`, `.gitignore`, ruff/mypy toolchain
- Phase 1: all SQLAlchemy models (`admins`, `roles`, `permissions`, `role_permissions`,
  `admin_roles`, `subscribers`, `plans`, `nas_devices`, `invoices`, `payments`, `audit_log`),
  FreeRADIUS standard schema via official `schema.sql`, initial Alembic migration
- Phase 2: admin auth (argon2, JWT access + refresh, logout/revocation, auth rate limiting)
- Phase 3: RBAC (`require_permission` dependency, Redis-cached permission set, 60s TTL,
  seeded `super_admin` + `auditor` roles, explicit permission check on every endpoint)
- Phase 4: API conventions layer (envelope, versioning, layering rules, `exceptions.py`)
- Phase 5: subscribers CRUD with `radcheck` coupling in one transaction
- Phase 6: plans with `radgroup` coupling (plan change reflected in `radgroupcheck`/`radgroupreply`)
- Phase 7: NAS devices CRUD, Fernet-encrypted secrets at rest, direct `nas`-table coupling
- Phase 8: slowapi + Redis rate limiting, tiered (auth strict, writes moderate, reads loose), 429 + `Retry-After`
- Phase 9: live sessions from `radacct`, CoA disconnect via pyrad (RFC 5176)
- Phase 10: billing — pricing/proration, invoice generation, payment status transitions,
  APScheduler job for invoice generation
- Phase 11: FreeRADIUS abuse protection (`radpostauth` tracking + unlang lockout), `/freeradius/README.md`
- Phase 12: Next.js dashboard — subscribers, plans, sessions, invoices, NAS, admin/role screens
- Phase 13: CI workflow, hardening pass, end-to-end smoke test

### Build order (demo spine first)

Work is sequenced so the demo-critical path is complete before peripheral items
are attempted. Tests are written as each section lands, per CLAUDE.md.

| Window | Work |
|---|---|
| Days 0–1 | Foundation: scaffolding, docker-compose, models + `audit_log`, FreeRADIUS `schema.sql`, initial Alembic migration (upgrade/downgrade both clean), API conventions layer, model-constraint unit tests |
| Days 1–2 | Auth + RBAC: argon2 hashing, JWT access+refresh, login/refresh/logout, role/permission seed, `require_permission` on every route, Redis permission cache (60s TTL); full auth + RBAC tests |
| Days 2–3 | Core resources: subscribers CRUD + `radcheck` coupling, plans + `radgroup` coupling, NAS devices + Fernet secrets + `nas` coupling, slowapi tiered rate limiting; tests per section |
| Days 3–4 | Sessions, billing, RADIUS hardening: live sessions from `radacct`, pyrad CoA disconnect, invoices + payments + APScheduler job, abuse-protection policy + `/freeradius/README.md`; tests per section |
| Days 4–5 | Frontend + polish: Next.js dashboard (all screens), CI workflow, human README, end-to-end smoke test |

### Cut candidates — only if the clock forces it

Built last, so a slip never touches the demo. If we run out of runway, this is the
order in which things are dropped, and the user is told immediately:

1. CI workflow (report-only)
2. Abuse-policy edge cases (core lockout stays)
3. Dashboard visual polish (functionality stays)
4. CoA live test against the real NAS (pyrad code still ships, tested via unit/integration)

## 4. Architecture

```
Next.js + shadcn/ui  <-->  FastAPI (REST API)  <-->  PostgreSQL  <-->  FreeRADIUS (sql module)
      (dashboard)         [RBAC + rate limit]        (shared DB)      (AAA on UDP 1812/1813)
                                  |
                                  v
                          Redis
                          - rate limiter state
                          - permission cache (60s TTL)
                          - APScheduler job store
```

- **FreeRADIUS and FastAPI are separate processes sharing the same PostgreSQL database.**
  FastAPI never proxies RADIUS packets; no custom RADIUS server; no XML-RPC/RPC bridge.
- **Direct coupling:** FastAPI writes subscriber credentials and plan attributes straight
  into FreeRADIUS's standard schema (`radcheck`, `radgroupcheck`, `radgroupreply`,
  `radusergroup`) in the same transaction as our own tables. No sync/ETL layer.
- **Identity domains are separate:** admin users (JWT + RBAC) vs. subscriber accounts
  (authenticated by FreeRADIUS against NAS devices). Never conflated.

## 5. Key Decisions (pinned)

Resolved during brainstorming; folded into CLAUDE.md during Phase 0:

1. **Name:** NetGrid.
2. **API conventions:** all routes under `/api/v1/...`; errors always
   `{"error": {"code": "SUBSCRIBER_NOT_FOUND", "message": "..."}}` with proper HTTP
   status; success responses are plain data; list endpoints return
   `{items, total, page, page_size}`. Centralized in `app/core/exceptions.py` + handlers.
3. **Layering:** routers are thin (parse/validate → call services); all DB access lives
   in services; services never import from `api/`.
4. **NAS ↔ `nas` table:** direct coupling — `nas_devices` and `nas` rows written in one
   transaction. Shared secrets encrypted at rest with **Fernet** (key in `.env`).
5. **CoA/disconnect:** FastAPI sends an RFC 5176 Disconnect-Request directly via **pyrad**
   — a client-library call, not a bridge.
6. **Password hashing:** `passlib` `CryptContext(schemes=["argon2"])`.
7. **RBAC cache:** permission set cached in Redis with 60s TTL, invalidated on role change.
8. **Test DB:** real Postgres via a docker-compose test service (dedicated database),
   never SQLite.
9. **radacct/radcheck hardening:** unique index on `radcheck(username, attribute)`;
   indexes on `radacct(username)`, `radacct(acctstoptime)`, `radacct(framedipaddress)`
   in the initial migration.
10. **Abuse protection:** failed-auth tracking via `radpostauth` into a small table +
    unlang lockout policy (lock out after N failures within a window, per username and
    per NAS); documented in `/freeradius/README.md`.

## 6. Data Model

Own schema (SQLAlchemy + Alembic):

- `admins`, `roles`, `permissions`, `role_permissions`, `admin_roles` — RBAC
- `subscribers` — profile/status/billing metadata (not credentials)
- `plans` — bandwidth/quota/price/duration; maps 1:1 to a RADIUS group
- `nas_devices` — router inventory, Fernet-encrypted shared secrets
- `invoices`, `payments` — billing
- `audit_log` — `(id, admin_id, action, resource, resource_id, metadata jsonb, created_at)`

FreeRADIUS schema (via official `schema.sql`, exact names preserved, never hand-modeled
except read-only mappings where the app queries them):

- `radcheck`, `radreply`, `radacct`, `radgroupcheck`, `radgroupreply`, `radusergroup`

## 7. Error Handling

- `app/core/exceptions.py` defines domain exceptions with stable string codes
  (e.g. `SUBSCRIBER_NOT_FOUND`, `PLAN_IN_USE`, `INVALID_CREDENTIALS`).
- FastAPI exception handlers map them to the `{"error": {"code", "message"}}` envelope.
- Rate limiting returns `429` with `Retry-After`.
- RBAC denial returns `403` with a permission code.

## 8. Testing Strategy

- pytest + pytest-asyncio + httpx `AsyncClient`; unit and integration per section.
- Test DB: real Postgres (dedicated docker-compose service) — no SQLite divergence.
- Redis available to integration tests for rate limiting and permission cache.
- Spine tests are highest priority: admin auth, RBAC enforcement/revocation,
  subscriber→`radcheck` coupling, plan→`radgroup` coupling, invoice math.
- Frontend: Vitest + React Testing Library for forms and sort/filter tables.

## 9. Success Criteria

- Demo narrative (Section 2) works end-to-end against real services.
- Every feature in scope exists and is demoable.
- Spine tests green; migrations `upgrade head` / `downgrade` both clean.
- CLAUDE.md updated with the pinned decisions and the recommendations table cleaned up.
- If cuts are forced, they come from the ordered cut list and are communicated immediately.

## 10. Out of Scope (explicitly deferred, report fodder)

- Distributed queue (Celery) — APScheduler only, unless a concrete need appears
- Multi-tenant/white-label features
- Subscriber-facing self-service portal
- Production deployment hardening (TLS termination, backup strategy)
