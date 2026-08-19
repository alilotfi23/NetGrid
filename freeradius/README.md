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

## Abuse protection

Failed-auth tracking / lockout policy (per-subscriber or per-NAS brute-force
mitigation) is not yet implemented — it arrives with Phase 11
(`radpostauth` logging or an `unlang` policy), and this section will document
the chosen approach then.
