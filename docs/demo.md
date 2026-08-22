# Demo walkthrough: from NAS auth to overage invoice

This guide walks the seeded demo dataset end to end through the three layers of
the platform and proves the full data-cap lifecycle with real data:

1. **RADIUS auth** — a simulated NAS authenticates against FreeRADIUS, which
   checks the shared Postgres (`radcheck`) and replies `Access-Accept`.
2. **Usage visibility** — that traffic lands in `radacct`, which the dashboard
   and the usage API turn into consumption-vs-quota numbers.
3. **Monetization & enforcement** — over-quota traffic becomes a per-GB
   **overage surcharge invoice**, and an opt-in job **disconnects** breaching
   sessions over CoA.

Everything below is copy-pasteable and safe: seeding is idempotent, and the
overage/enforcement exercises use a throwaway subscriber you delete at the end.

---

## 0. Prerequisites

- Docker Desktop running (the whole stack lives in Compose)
- Python 3.12+ for the seed script (or run it inside the backend container)
- Free ports `5432`, `6379`, `8000`, `3000`, and UDP `1812/1813`

## 1. Start the stack and seed the demo data

```bash
# Full stack: postgres, redis, freeradius, backend, frontend, sim-nas
docker compose up -d --build

# Seed plans, NAS devices, subscribers, 13 months of invoices/payments,
# overdue flips, and 5 live sessions. Idempotent — safe to re-run.
cd backend && python scripts/seed_dev.py
```

What the seed creates (only when absent — re-runs are no-ops per section):

| Section | Contents |
|---|---|
| Plans | **Starter** 10 Mbps / 200 GB, **Pro** 25 Mbps / 500 GB, **Fiber** 50 Mbps / 1000 GB — all with `enforce_quota` on and **$0.50/GB overage** — plus decommissioned **Legacy ADSL** (inactive, no quota) |
| NAS devices | Edge Router 1 + 2 (active MikroTik), Legacy Cisco (inactive) — mirrored into FreeRADIUS's `nas` table |
| Subscribers | 12 accounts (8 active, 2 suspended, 2 expired; 7 of the active ones on plans) with real `radcheck` credentials |
| Invoices | 13 months of base invoices + backdated payments (paid/overdue mix) so the revenue trend renders fully |
| Sessions | 5 open `radacct` rows with real octet counters for the live-sessions cards |

Bootstrap admin: **`superadmin` / `netgrid-admin`** (change it after first login).

Verify everything is up:

```bash
curl http://localhost:8000/api/v1/health        # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000   # 200
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

## 2. RADIUS auth, end to end (sim-nas)

The `sim-nas` container plays both NAS roles with pure-Python, zero-dependency
implementations:

- **Auth client (RFC 2865)** — sends an Access-Request to FreeRADIUS every
  30 seconds;
- **CoA server (RFC 5176)** — listens on UDP 3799 and answers every authentic
  Disconnect/CoA-Request with a real Disconnect-ACK, so the platform's pyrad
  disconnect path gets an ACK instead of a timeout. It verifies the request
  authenticator and Message-Authenticator against the shared NAS secret, and
  drops (never replies to) packets that fail — exactly like a real NAS.

Register it as a NAS device and seed a `demo-user` subscriber in one command:

```bash
python scripts/setup-mikrotik-nas.py
```

The script: detects the container's IP on the `netgrid` network → registers it
via the API (`POST /api/v1/nas-devices`, idempotent) → seeds `demo-user` /
`demo-pass` into `radcheck` → clears any lockout residue → runs `radtest` to
confirm `Access-Accept`.

Watch the live auth path:

```bash
docker compose logs -f sim-nas
# [12:00:01] #   42  demo-user → Access-Accept  ✓
```

Every 30 seconds you're seeing the full loop:
`sim-nas → FreeRADIUS (UDP 1812) → rlm_sql → radcheck → Access-Accept`.

Peek at what FreeRADIUS actually checks:

```bash
docker compose exec postgres psql -U netgrid -d netgrid \
  -c "SELECT username, attribute, op, value FROM radcheck WHERE username='demo-user';"

docker compose exec postgres psql -U netgrid -d netgrid \
  -c "SELECT username, reply, authdate FROM radpostauth ORDER BY authdate DESC LIMIT 5;"
```

`radpostauth` also drives the **failed-auth lockout policy**
(`freeradius/raddb/policy.d/lockout`): 10 failures in 5 minutes and FreeRADIUS
starts rejecting that username — that's the RADIUS-side brute-force protection.
To see it in action:

```bash
docker compose exec freeradius sh -c \
  'for i in $(seq 1 10); do radtest demo-user wrongpass 127.0.0.1 1812 testing123 >/dev/null; done'
docker compose exec freeradius radtest demo-user demo-pass 127.0.0.1 1812 testing123  # Access-Reject (locked)
```

Clear the lockout by deleting the failure rows:

```bash
docker compose exec postgres psql -U netgrid -d netgrid \
  -c "DELETE FROM radpostauth WHERE username='demo-user';"
```

## 3. Tour the dashboard

Open http://localhost:3000 and log in as `superadmin`.

- **KPI strip** — active subscribers, live sessions, revenue, overdue. Polls
  every 30s with a subtle "updated Xs ago" stale indicator.
- **Data cap usage card** — per-plan-assigned-subscriber progress bars (green
  <80%, amber 80–100%, red over quota) + rollup, live-polling.
- **Live sessions** — the 5 seeded `radacct` rows with NAS/username/duration.
  Try the **Disconnect** action on one — it sends a real RFC 5176
  Disconnect-Request via `pyrad` to the NAS IP. Sessions pointing at the
  seeded `192.168.0.x` routers still time out (those IPs don't exist here),
  but a session whose `nasipaddress` is the sim-nas container IP gets a real
  **Disconnect-ACK** — the audit log records `result: "ack"` (see §6).
- **Revenue trend** — 12 months of payments, fully populated by the seed.
- **Recent activity** — live audit feed, with actor links into the pre-filtered
  audit log.
- **Subscribers → any profile** — month-by-month **Usage history** table
  (down/up/total vs quota per calendar month).

## 4. The usage read path

```bash
# Login once, reuse the token in the rest of the guide
TOK=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"superadmin","password":"netgrid-admin"}' \
  | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# Current-month consumption vs quota for every plan-assigned subscriber
curl -s http://127.0.0.1:8000/api/v1/usage -H "Authorization: Bearer $TOK" | python -m json.tool
```

Each item carries `total_gb`, `quota_gb`, `pct_used`, `session_count`, and the
rollup sums consumed GB + over-quota count. The same numbers drive the
dashboard card.

## 5. Overage surcharge, end to end ⭐

The money shot: bill per-GB for usage beyond quota. `radacct` is owned by
FreeRADIUS, so we fabricate the traffic directly in SQL (a real NAS writes the
same rows via Accounting-Requests).

**Scenario:** `dorothy.vaughan` is on Starter (200 GB quota, $0.50/GB overage).
Fabricate 230 GiB of traffic in the **previous** calendar month — the period
the overage job bills by default:

```bash
docker compose exec postgres psql -U netgrid -d netgrid <<'SQL'
INSERT INTO radacct (acctsessionid, acctuniqueid, username, nasipaddress,
                     acctstarttime, acctstoptime, acctsessiontime,
                     acctinputoctets, acctoutputoctets, framedipaddress)
VALUES ('demo-overage-1', 'demo-overage-uniq-1', 'dorothy.vaughan', '192.168.0.10',
        date_trunc('month', now() - interval '1 month') + interval '5 days',
        date_trunc('month', now() - interval '1 month') + interval '5 days 1 hour',
        3600,
        236223201280::bigint,   -- 220 GiB down
        10737418240::bigint,    --  10 GiB up
        '10.20.0.14');
SQL
```

> The `::bigint` cast matters — 220 GiB overflows a 32-bit int, and the quota
> math in the usage service counts GiB (1024³ bytes).

Check the usage report sees it for that window:

```bash
# The default report is current-month; the overage job's window is the
# previous month, so verify via the per-subscriber history endpoint:
curl -s "http://127.0.0.1:8000/api/v1/subscribers/5/usage?months=2" \
  -H "Authorization: Bearer $TOK" | python -m json.tool
```

(Subscriber id 5 is `dorothy.vaughan` — the seventh seed row; confirm with
`GET /api/v1/subscribers?q=dorothy` if unsure.) The previous month should show
~230 GB consumed vs a 200 GB quota → ~115% used.

Now generate the surcharge — 30 GiB over × $0.50/GB = **$15.00**:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/invoices/overage/generate \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{}' \
  | python -m json.tool        # {"created": 1}

# Re-run — idempotent, nothing new:
curl -s -X POST http://127.0.0.1:8000/api/v1/invoices/overage/generate \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{}' \
  | python -m json.tool        # {"created": 0}
```

Find and inspect the surcharge:

```bash
curl -s "http://127.0.0.1:8000/api/v1/invoices?subscriber_id=5&status=issued" \
  -H "Authorization: Bearer $TOK" | python -m json.tool
```

It has `"kind": "overage"` and `amount: 15.00` — the dashboard badges it
**surcharge** in the invoices list and detail. The overdue sweep later flips it
to `overdue` like any other unpaid invoice.

**Cleanup** (removes the fabricated traffic + surcharge):

```bash
docker compose exec postgres psql -U netgrid -d netgrid -c \
  "DELETE FROM radacct WHERE acctuniqueid='demo-overage-uniq-1';"
docker compose exec postgres psql -U netgrid -d netgrid -c \
  "DELETE FROM invoices WHERE kind='overage';"
```

## 6. Quota enforcement (CoA disconnect)

The enforcement job (every 5 min by default, `quota_enforcement_interval_minutes`)
polls the usage report and disconnects live sessions of subscribers **at or
over quota on a plan with `enforce_quota` enabled** (all three demo plans have
it on), with a 30-minute per-subscriber cooldown between actions.

Fabricate a **current-month** over-quota session for `grace.hopper` (Pro, 500 GB,
~3.2 GiB seeded usage — add 510 GiB so she's clearly over). Point it at the
**sim-nas container IP** so the CoA disconnect actually lands somewhere (the
seeded `192.168.0.x` routers are unreachable in this environment):

```bash
# The IP the setup script registered as a NAS (docker inspect if unsure)
SIM_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' netgrid-sim-nas-1)

docker compose exec postgres psql -U netgrid -d netgrid <<SQL
INSERT INTO radacct (acctsessionid, acctuniqueid, username, nasipaddress,
                     acctstarttime, acctsessiontime,
                     acctinputoctets, acctoutputoctets, framedipaddress)
VALUES ('demo-enforce-1', 'demo-enforce-uniq-1', 'grace.hopper', '$SIM_IP',
        now() - interval '1 hour', 3600,
        515396075520::bigint,   -- 480 GiB down
        32212254720::bigint,    --  30 GiB up
        '10.20.0.13');
SQL
```

Run one sweep immediately (instead of waiting for the scheduler):

```bash
cd backend && .venv/Scripts/python.exe -c "
import asyncio
from app.core.db import get_session
from app.jobs.quota_enforcement import run_quota_enforcement

async def main():
    async for session in get_session():
        print(await run_quota_enforcement(session))

asyncio.run(main())
"
# QuotaEnforcementSummary(checked=..., over_quota=1, enforced=1,
#   sessions_disconnected=0, sessions_failed=1, ...)
```

What to expect:

- **`over_quota=1, enforced=1, sessions_disconnected=1`** — the job found the
  breach, sent the Disconnect-Request to the sim-nas, and the responder
  verified it (request authenticator + Message-Authenticator against the NAS
  shared secret) and replied Disconnect-ACK.
- The **radacct row stays open** even after the ACK — the sim-nas is a
  responder, not a router: it doesn't emit the Accounting-Stop that would
  close the session (a real NAS does). The ACK is the proof the CoA path
  works end to end; `disconnect_service` never writes `radacct`.
- Failure tolerance is unchanged: a session whose NAS is unreachable counts
  as `sessions_failed` without aborting the sweep, and the outcome lands in
  the audit trail.

Check the audit trail — each enforced subscriber gets one `quota_enforced`
entry (usage vs quota + per-session outcomes) alongside the transport-level
`disconnect` entries:

```bash
curl -s "http://127.0.0.1:8000/api/v1/audit-logs?action=quota_enforced&page_size=5" \
  -H "Authorization: Bearer $TOK" | python -m json.tool
```

Re-run the sweep within 30 minutes and `skipped_cooldown=1` — the cooldown is
keyed on these audit rows, so a NAS that never sends Accounting-Stop isn't
hammered every interval.

**Cleanup:**

```bash
docker compose exec postgres psql -U netgrid -d netgrid -c \
  "DELETE FROM radacct WHERE acctuniqueid='demo-enforce-uniq-1';"
```

## Reference

**Seeded demo credentials**

| Who | Credential |
|---|---|
| Dashboard admin | `superadmin` / `netgrid-admin` |
| sim-nas subscriber | `demo-user` / `demo-pass` |
| Subscribers | `ada.lovelace` … `leslie.lamport`, passwords `demo-pass-<first name>` (e.g. `demo-pass-ada`) |

**Plans and their data-cap settings** (all three active plans: `enforce_quota` on,
`overage_price_per_gb` = $0.50)

| Plan | Quota | Overage math |
|---|---|---|
| Starter | 200 GB | 30 GiB over → $15.00 |
| Pro | 500 GB | 10 GiB over → $5.00 |
| Fiber | 1000 GB | 1 GiB over → $0.50 |

**The jobs involved** (all in `app/jobs/`, schedules in
`app/jobs/invoice_generation.py`):

| Job | Schedule | What it does |
|---|---|---|
| `monthly-invoice-generation` | 1st, 00:05 UTC | base invoices (idempotent, prorated) |
| `daily-overdue-sweep` | daily, 00:10 UTC | issued → overdue flips |
| `overage-billing` | 2nd, 00:15 UTC | per-GB surcharges for the previous month |
| `quota-enforcement` | every 5 min | CoA-disconnect subscribers at/over quota |

**Key endpoints used in this guide** (all under `/api/v1`, all RBAC-gated):

| Endpoint | Permission | Used for |
|---|---|---|
| `POST /auth/login` | — | getting the token |
| `GET /usage` | `usage:read` | consumption vs quota report |
| `GET /subscribers/{id}/usage?months=N` | `subscribers:read` | month-by-month history |
| `POST /invoices/overage/generate` | `invoices:write` | manual overage run |
| `GET /invoices?subscriber_id=&status=` | `invoices:read` | finding the surcharge |
| `GET /audit-logs?action=quota_enforced` | `audit_logs:read` | enforcement trail |
| `POST /nas-devices` | `nas_devices:write` | registering the sim-nas |

**Tearing down** — `docker compose down` keeps the postgres volume;
`docker compose down -v` also wipes the database (then re-seed with step 1).
