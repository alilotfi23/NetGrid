# FreeRADIUS (NetGrid AAA layer)

FreeRADIUS is the AAA server: it authenticates subscriber accounts (PAP/CHAP/
MSCHAPv2) against NAS devices on UDP 1812/1813. It shares the NetGrid
PostgreSQL database with the FastAPI backend and reads credentials from the
standard FreeRADIUS schema via its `sql` module (`authcheck_table = "radcheck"`,
see `raddb/mods-enabled/sql`). FastAPI writes subscriber credentials straight
into `radcheck` in the same transaction as the `subscribers` row (the direct
coupling decision — see `../CLAUDE.md`); FreeRADIUS never talks to FastAPI.

## Schema notes

The stock `raddb/mods-config/sql/main/postgresql/schema.sql` declares rad*
columns with mixed-case names (`UserName`, `Attribute`, `Value`), but they are
unquoted, so PostgreSQL folds them to lowercase. The effective schema —
what both FreeRADIUS's queries and the FastAPI `RadCheck` model use — is:

```
radcheck:  id, username, attribute, op, value
```

Always use lowercase in psql checks (e.g. `WHERE username = 'bob'`), never
`"UserName"`.

## Live verification: subscriber auth lifecycle with radtest

This is the end-to-end proof of the coupling: create a subscriber through the
FastAPI API, then let FreeRADIUS itself authenticate (or reject) them against
the rows FastAPI wrote. Requires the compose stack up (`docker compose up -d
postgres redis freeradius backend`).

The test NAS shared secret in the container image is `testing123`; radtest runs
against `127.0.0.1:1812` inside the freeradius container.

```bash
# 1. login as an admin to mint a bearer token for the API
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"superadmin","password":"netgrid-admin"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

# 2. create a subscriber -> one radcheck row (Cleartext-Password := <pw>)
SUB=$(curl -s -X POST http://localhost:8000/api/v1/subscribers -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"username":"p5test","full_name":"Plan Five Tester","password":"radpass123"}')
SUB_ID=$(echo "$SUB" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT username, attribute, op, value FROM radcheck WHERE username='p5test';"
# expect: 1 row — p5test | Cleartext-Password | := | radpass123

# 3. real RADIUS auth -> Access-Accept
docker compose exec freeradius radtest p5test radpass123 127.0.0.1 0 testing123
# expect: "Received Access-Accept"

# 4. suspend -> Auth-Type := Reject row appears; RADIUS now rejects
curl -s -X PATCH http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"status":"suspended"}'
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT username, attribute, op, value FROM radcheck WHERE username='p5test';"
# expect: 2 rows — Cleartext-Password + Auth-Type := Reject
docker compose exec freeradius radtest p5test radpass123 127.0.0.1 0 testing123
# expect: "Received Access-Reject"

# 5. reactivate -> Reject row removed; RADIUS accepts again
curl -s -X PATCH http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"status":"active"}'
docker compose exec freeradius radtest p5test radpass123 127.0.0.1 0 testing123
# expect: "Received Access-Accept"

# 6. delete -> radcheck rows gone (profile + credentials removed atomically)
curl -s -o /dev/null -w "delete: %{http_code}\n" \
  -X DELETE http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH"
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT count(*) FROM radcheck WHERE username='p5test';"
# expect: 0
```

Reading radtest output: an `Access-Reject` is a **successful** rejection —
grep for `Received Access-Accept` / `Received Access-Reject` rather than
relying on the process exit code, and remember that suspending a subscriber
turns a previously valid credential into a deliberate `Access-Reject`.

## Live verification: NAS-table client lifecycle with radclient

NAS devices are not configured in `clients.conf` — the `sql` module runs with
`read_clients = yes` (see `raddb/mods-available/sql`), so at startup every
active `nas_devices` row (mirrored to the FreeRADIUS `nas` table by FastAPI in
the same transaction) becomes a RADIUS client keyed on its `ip_address`.
This section proves that coupling end-to-end: create a NAS through the API,
restart FreeRADIUS, authenticate from a source only the nas-table client
matches, then deactivate it and watch the probe get dropped.

**Why the probe needs its own IP.** `clients.conf` ships a `netgrid_network`
client covering `172.28.0.0/16` so any compose container can reach FreeRADIUS.
A nas-table row for one IP is a `/32` and wins by best-match, so a request
from the probe IP is handled by the nas-table client — not the network one.
Signing the request with the nas row's *own* secret (different from the
network client's `netgrid_radius_secret`) and receiving `Access-Accept` is
therefore proof that the nas-table client matched; if it hadn't, the
Message-Authenticator check would fail and the packet would be dropped.

The probe is a throwaway container spawned from the `netgrid-freeradius`
image itself, so `radclient` and its dictionaries are already installed — no
binary copying needed. `--entrypoint sleep` just skips starting radiusd.

```bash
# 1. login as an admin to mint a bearer token for the API
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"superadmin","password":"netgrid-admin"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

# 2. an active subscriber to authenticate (same pattern as the radtest section)
curl -s -X POST http://localhost:8000/api/v1/subscribers -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"username":"nastest","full_name":"NAS Lifecycle Tester","password":"radpass123"}' > /dev/null

# 3. probe container on the netgrid network (gets a fresh 172.28.0.x IP)
PROBE=$(docker run -d --rm --entrypoint sleep netgrid-freeradius 600)
docker network connect netgrid_netgrid "$PROBE"
PROBE_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$PROBE" | awk '{print $2}')
FR_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' netgrid-freeradius-1)
echo "probe=$PROBE_IP freeradius=$FR_IP"

# 4. create the NAS device for the probe IP via the API
NAS=$(curl -s -X POST http://localhost:8000/api/v1/nas-devices -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"nasprobe\",\"ip_address\":\"$PROBE_IP\",\"shortname\":\"nasprobe\",\"secret\":\"nasprobe-secret\",\"nas_type\":\"other\",\"ports\":1812}")
NAS_ID=$(echo "$NAS" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
# expect: 201, and the response carries NO "secret" field

# 5. confirm the mirrored nas row — plaintext secret, because FreeRADIUS must
#    recover it for PAP/CHAP (the encrypted copy lives in nas_devices)
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT nasname, shortname, secret FROM nas WHERE nasname='$PROBE_IP';"

# 6. restart FreeRADIUS so read_clients loads the nas row as a client
sleep 2
docker compose restart freeradius
docker compose logs --since 30s freeradius | grep -E "Client .*\(sql\) added"
# expect: rlm_sql (<probe ip>): Client "nasprobe" (sql) added

# 7. real RADIUS auth from the probe, signed with the nas row's secret
sleep 2
docker exec "$PROBE" sh -c "printf 'User-Name=nastest, User-Password=radpass123' | radclient -x $FR_IP:1812 auth nasprobe-secret"
# expect: "Received Access-Accept"

# 8. deactivate -> the nas row is removed in the same transaction
curl -s -X PATCH http://localhost:8000/api/v1/nas-devices/$NAS_ID -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"is_active":false}' > /dev/null
docker compose exec -T postgres psql -U netgrid -d netgrid \
  -c "SELECT count(*) FROM nas WHERE nasname='$PROBE_IP';"
# expect: 0

# 9. restart and retry the probe -> FreeRADIUS no longer knows this NAS
sleep 2
docker compose restart freeradius
sleep 2
docker exec "$PROBE" sh -c "timeout 8 sh -c \"printf 'User-Name=nastest, User-Password=radpass123' | radclient -x $FR_IP:1812 auth nasprobe-secret\""
# expect: NO "Received" line. The /32 nas client is gone, so the /16 network
# client matches instead and the stale secret fails the Message-Authenticator
# check — the packet is dropped without a response, and FreeRADIUS logs:
#   Dropping packet without response because of error: Received packet from
#   <probe ip> with invalid Message-Authenticator ... (from client netgrid_network)

# 10. cleanup: delete the NAS (removes the nas row), the subscriber, and the probe
curl -s -o /dev/null -w "delete: %{http_code}\n" \
  -X DELETE http://localhost:8000/api/v1/nas-devices/$NAS_ID -H "$AUTH"
SUB_ID=$(curl -s "http://localhost:8000/api/v1/subscribers?q=nastest" -H "$AUTH" \
  | python -c "import sys,json;d=json.load(sys.stdin);print(d['items'][0]['id'] if d['items'] else '')")
if [ -n "$SUB_ID" ]; then
  curl -s -o /dev/null -X DELETE http://localhost:8000/api/v1/subscribers/$SUB_ID -H "$AUTH"
fi
docker rm -f "$PROBE"
```

Reading radclient output: the deactivation step is the interesting one — a
**silent drop is the expected success** once the NAS is decommissioned, and the
FreeRADIUS log line quoted above is how you confirm it. While the nas-table
client exists, `Received Access-Accept` (or `Access-Reject` for a bad
subscriber credential) is the signal, exactly as with radtest.

## Abuse protection (Phase 11) — failed-auth lockout

**Approach: per-username lockout driven by `radpostauth`, enforced by a small
`unlang` policy (`raddb/policy.d/lockout`, invoked from the `authorize`
section of `sites-enabled/default`).**

How it works:

- Every authentication attempt is already written to `radpostauth` by the
  `sql` module in `post-auth` (reply = `Access-Accept` / `Access-Reject`).
- In `authorize` (after `pap`, so its `Auth-Type := Reject` wins over the
  credential modules), the policy counts recent failures for the requesting
  username:

  ```unlang
  Tmp-Integer-0 := "%{sql:SELECT count(*) FROM radpostauth WHERE
      username = '%{User-Name}' AND reply = 'Access-Reject' AND
      authdate > now() - interval '5 minutes'}"
  ```

- If the count is >= 10, the policy sets `control:Auth-Type := Reject` and a
  `Reply-Message`. `Auth-Type = Reject` has no handler in the `authenticate`
  section, so FreeRADIUS answers **Access-Reject before the credential is
  even checked** and the `Post-Auth-Type REJECT` section logs the attempt —
  keeping the counter at/above threshold while an attacker keeps hammering.

There is **no separate lockout table by design**: the lockout *is* the
recent-failure count, so it self-expires as failures age out of the 5-minute
window (no cleanup job, no clock skew between a lock write and an unlock
read). A legitimate user who mistypes 10 times is locked out for at most 5
minutes. Tunables: `>= 10` (threshold) and `interval '5 minutes'` (window)
in `raddb/policy.d/lockout`.

Notes and known limits:

- **Scope: per username.** Per-NAS / per-source-IP throttling is not
  implemented — `clients.conf`-level limits (`max_connections`) still apply
  per client, and this policy covers the credential-guessing vector.
- **The username is interpolated into the SQL query** (same as the stock
  FreeRADIUS brute-force policy, wiki.freeradius.org). A crafted `User-Name`
  can only corrupt the count for its own request (worst case: an attacker
  locks themselves out or bypasses their own lockout) — the result is used
  solely as a threshold for the caller's own packet, never to read or modify
  data. Verified by `test_hostile_username_does_not_break_lockout_query`.
- **`radpostauth` stores attempted passwords in plaintext** (standard
  FreeRADIUS schema behaviour — the lockout counter depends on the table).
  This is the stock `schema.sql`; treat the database accordingly.
- The policy fails open: if the SQL query errors, `Tmp-Integer-0` is left
  unset and the request proceeds (auth itself would fail anyway if the DB is
  down, since `sql` also does the credential lookup).

### Verifying with radtest (scripted checks in `backend/tests/radius`)

The pytest module `backend/tests/radius/test_lockout.py` drives the whole
lifecycle through `radtest` + `psql` against the compose stack (no Python
RADIUS client — it exercises the exact production path):

```bash
docker compose up -d --wait postgres freeradius
cd backend && pytest tests/radius -q
```

Checks: baseline accept; 10 wrong guesses; the 11th attempt with the
**correct** password is rejected (lockout short-circuits the credential
check); all 11 rejections are in `radpostauth`; clearing the failure rows
(simulating window expiry) lifts the lockout; successful auths never count
toward the threshold; unknown usernames are protected too; and a hostile
`User-Name` cannot break the policy or the server.

Manual spot-check (same flow, no pytest):

```bash
# seed a subscriber the way the FastAPI service does
docker compose exec -T postgres psql -U netgrid -d netgrid -c \
  "INSERT INTO radcheck (username, attribute, op, value) VALUES
   ('lockprobe', 'Cleartext-Password', ':=', 'correct-horse')"
# 10 wrong guesses, then a correct one — it is rejected (locked out)
docker compose exec freeradius radtest lockprobe wrongpass 127.0.0.1 0 testing123
# ... x10 ...
docker compose exec freeradius radtest lockprobe correct-horse 127.0.0.1 0 testing123
# expect: "Received Access-Reject"
# cleanup
docker compose exec -T postgres psql -U netgrid -d netgrid -c \
  "DELETE FROM radcheck WHERE username='lockprobe'; DELETE FROM radpostauth WHERE username='lockprobe';"
```
