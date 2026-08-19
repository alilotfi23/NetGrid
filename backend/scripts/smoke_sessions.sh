#!/usr/bin/env bash
#
# smoke_sessions.sh — curl-based smoke test for the NetGrid sessions API.
#
# Walks the live-session surface end to end against a running backend:
#   login -> list (shape) -> auth errors -> disconnect error paths
#   (404/422/409 closed/409 no-NAS/502 timeout) -> RBAC (auditor read-only,
#   limited admin denied).
#
# Sessions are read-only views over FreeRADIUS's radacct table, which the
# API never writes — so the disconnect-path checks need seeded radacct rows.
# The script seeds them via psql (see PSQL_CMD). If the database is not
# reachable, the DB-backed checks are skipped with a note and the
# API-only checks still run.
#
# Prerequisites: curl + jq on PATH; backend reachable at $BASE_URL; seeded
# admin exists (superadmin / netgrid-admin by default).
#
# Usage:
#   BASE_URL=http://localhost:8000 ./smoke_sessions.sh
#   # with a non-compose DB:
#   PSQL_CMD="psql postgres://netgrid:netgrid@localhost:5432/netgrid" ./smoke_sessions.sh
#
# Exit code 0 = every check passed; 1 = one or more failed.
#
# Notes: login is rate-limited to 5/min/IP, so don't run this in a tight
# loop. The 502 check sends a real UDP packet to a TEST-NET address and
# waits for pyrad's timeout — expect it to take ~15s.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-superadmin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-netgrid-admin}"
# Command prefix used to run SQL against the NetGrid database. Defaults to
# docker compose exec on the postgres service; override with a psql URL.
PSQL_CMD="${PSQL_CMD:-docker compose exec -T postgres psql -U netgrid -d netgrid -v ON_ERROR_STOP=1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

command -v curl >/dev/null 2>&1 || { echo "FAIL  curl not found on PATH"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "FAIL  jq not found on PATH"; exit 1; }

pass=0
fail=0

check() {
    local label="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "PASS  $label"
        pass=$((pass + 1))
    else
        echo "FAIL  $label  (expected: $expected, got: $actual)"
        fail=$((fail + 1))
    fi
}

http_code() { curl -s --max-time 60 -o /dev/null -w '%{http_code}' "$@"; }

psql_run() { ( cd "$REPO_ROOT" && $PSQL_CMD -c "$1" ) 2>/dev/null; }
psql_value() { ( cd "$REPO_ROOT" && $PSQL_CMD -tA -c "$1" ) 2>/dev/null; }

# --- login ----------------------------------------------------------------
echo "== login ==================================================================="
LOGIN_JSON="$(curl -sf --max-time 30 -X POST "$BASE_URL/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")" \
    || { echo "FAIL  login (is the backend up at $BASE_URL?)"; exit 1; }
TOKEN="$(printf '%s' "$LOGIN_JSON" | jq -r '.access_token')"
[ -n "$TOKEN" ] && token_state=non-empty || token_state=empty
check "login issues access token" "non-empty" "$token_state"
AUTH="Authorization: Bearer $TOKEN"

# Unique names so a re-run never collides with leftovers from a previous run.
SUFFIX="$(date +%s)"
SMOKE_USER="smoke_user_${SUFFIX}"

# --- list shape (API-only, always runs) -----------------------------------
echo "== list (shape) ============================================================="
LIST="$(curl -sf --max-time 30 "$BASE_URL/api/v1/sessions" -H "$AUTH")"
check "sessions list returns 200 shape" "true" \
    "$(printf '%s' "$LIST" | jq -r '(.items | type) == "array" and (.stats.total | type) == "number"')"
check "stats carries by_nas array" "true" \
    "$(printf '%s' "$LIST" | jq -r '(.stats.by_nas | type) == "array"')"

# --- auth errors (API-only) -------------------------------------------------
echo "== auth errors ============================================================="
CODE="$(http_code "$BASE_URL/api/v1/sessions")"
check "401 list without token" "401" "$CODE"
CODE="$(http_code "$BASE_URL/api/v1/sessions/1/disconnect")"
check "401 disconnect without token" "401" "$CODE"

# --- disconnect error paths not needing the DB ------------------------------
echo "== disconnect error paths (no DB) =========================================="
CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/999999/disconnect" -H "$AUTH")"
check "404 unknown session" "404" "$CODE"
CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/not-an-int/disconnect" -H "$AUTH")"
check "422 non-integer session id" "422" "$CODE"

# --- DB-backed checks -------------------------------------------------------
echo "== db availability ==========================================================="
if [ "${SKIP_DB_CHECKS:-0}" = "1" ] || ! psql_run "SELECT 1;" >/dev/null; then
    echo "NOTE  database not reachable via PSQL_CMD — skipping seeded-session checks"
else
    echo "database reachable — seeding radacct rows"

    # --- seed --------------------------------------------------------------
    echo "== seed radacct ==============================================================="
    # radacct requires acctuniqueid NOT NULL UNIQUE + acctsessionid NOT NULL.
    # open session on a NAS with NO device (-> 409 no active NAS)
    OPEN_ID="$(psql_value "INSERT INTO radacct (acctsessionid, acctuniqueid, username, nasipaddress, acctstarttime, acctstoptime, acctsessiontime, acctinputoctets, acctoutputoctets, framedipaddress) VALUES ('smoke-${SUFFIX}-open', 'smoke-${SUFFIX}-open', '${SMOKE_USER}', '192.0.2.1', now() - interval '1 hour', NULL, 3600, 12345, 67890, '198.51.100.5') RETURNING radacctid;")"
    # closed session on the same NAS (-> 409 session no longer active)
    CLOSED_ID="$(psql_value "INSERT INTO radacct (acctsessionid, acctuniqueid, username, nasipaddress, acctstarttime, acctstoptime, acctsessiontime, acctinputoctets, acctoutputoctets, framedipaddress) VALUES ('smoke-${SUFFIX}-closed', 'smoke-${SUFFIX}-closed', '${SMOKE_USER}', '192.0.2.1', now() - interval '2 hours', now() - interval '1 hour', 3600, 12345, 67890, '198.51.100.5') RETURNING radacctid;")"
    # open session on a NAS we WILL register as a device (-> 502 timeout)
    DEV_OPEN_ID="$(psql_value "INSERT INTO radacct (acctsessionid, acctuniqueid, username, nasipaddress, acctstarttime, acctstoptime, acctsessiontime, acctinputoctets, acctoutputoctets, framedipaddress) VALUES ('smoke-${SUFFIX}-dev', 'smoke-${SUFFIX}-dev', '${SMOKE_USER}', '192.0.2.2', now() - interval '30 minutes', NULL, 1800, 111, 222, '198.51.100.6') RETURNING radacctid;")"
    check "seeded 3 radacct rows" "true" \
        "$([ -n "$OPEN_ID" ] && [ -n "$CLOSED_ID" ] && [ -n "$DEV_OPEN_ID" ] && echo true || echo false)"

    # --- read side ---------------------------------------------------------
    echo "== read side ==============================================================="
    LIST="$(curl -sf --max-time 30 "$BASE_URL/api/v1/sessions?q=$SMOKE_USER" -H "$AUTH")"
    check "search finds only the open session" "1" "$(printf '%s' "$LIST" | jq -r '.total')"
    check "list item carries the username" "$SMOKE_USER" \
        "$(printf '%s' "$LIST" | jq -r '.items[0].username')"
    check "list item resolves nas ip" "192.0.2.1" \
        "$(printf '%s' "$LIST" | jq -r '.items[0].nasipaddress')"

    # --- disconnect error paths needing rows ---------------------------------
    echo "== disconnect error paths (seeded) =========================================="
    CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/$CLOSED_ID/disconnect" -H "$AUTH")"
    check "409 disconnect on closed session" "409" "$CODE"
    CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/$OPEN_ID/disconnect" -H "$AUTH")"
    check "409 disconnect with no registered NAS" "409" "$CODE"

    # --- 502 timeout path (slow: real UDP + pyrad timeout) --------------------
    echo "== disconnect timeout path (slow, ~15s) ======================================"
    NAS="$(curl -sf --max-time 30 -X POST "$BASE_URL/api/v1/nas-devices" -H "$AUTH" \
        -H 'Content-Type: application/json' \
        -d "{\"name\":\"smoke_nas_${SUFFIX}\",\"ip_address\":\"192.0.2.2\",\"shortname\":\"smoke-nas-${SUFFIX}\",\"nas_type\":\"other\",\"secret\":\"smoketestsecret123\"}")"
    NAS_ID="$(printf '%s' "$NAS" | jq -r '.id')"
    check "nas device created" "true" "$([ -n "$NAS_ID" ] && [ "$NAS_ID" != "null" ] && echo true || echo false)"
    CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/$DEV_OPEN_ID/disconnect" -H "$AUTH")"
    check "502 disconnect times out against unreachable NAS" "502" "$CODE"
    # the attempt is still audited even when the NAS never answers
    curl -s --max-time 30 -o /dev/null -X DELETE "$BASE_URL/api/v1/nas-devices/$NAS_ID" -H "$AUTH" || true

    # --- cleanup radacct ------------------------------------------------------
    psql_run "DELETE FROM radacct WHERE acctsessionid LIKE 'smoke-${SUFFIX}-%';" || true
    echo "cleanup: radacct rows removed"
fi

# --- RBAC -------------------------------------------------------------------
echo "== rbac ======================================================================="
ROLES="$(curl -sf --max-time 30 "$BASE_URL/api/v1/roles" -H "$AUTH")"
AUDITOR_ROLE_ID="$(printf '%s' "$ROLES" | jq -r '.items[] | select(.name == "auditor") | .id')"
if [ -z "$AUDITOR_ROLE_ID" ] || [ "$AUDITOR_ROLE_ID" = "null" ]; then
    check "auditor role exists" "found" "missing"
else
    AUDITOR_USER="smoke_audit_${SUFFIX}"
    curl -s --max-time 30 -o /dev/null -X POST "$BASE_URL/api/v1/admins" -H "$AUTH" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$AUDITOR_USER\",\"email\":\"$AUDITOR_USER@netgrid.local\",\"password\":\"secret123\",\"role_ids\":[$AUDITOR_ROLE_ID]}"
    AUDITOR_TOKEN="$(curl -sf --max-time 30 -X POST "$BASE_URL/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$AUDITOR_USER\",\"password\":\"secret123\"}" | jq -r '.access_token')"
    check "auditor login" "non-empty" "$([ -n "$AUDITOR_TOKEN" ] && echo non-empty || echo empty)"
    CODE="$(http_code "$BASE_URL/api/v1/sessions" -H "Authorization: Bearer $AUDITOR_TOKEN")"
    check "auditor can list sessions" "200" "$CODE"
    CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/1/disconnect" -H "Authorization: Bearer $AUDITOR_TOKEN")"
    check "auditor cannot disconnect (403)" "403" "$CODE"

    # a limited admin with no sessions:read gets 403 on both list and disconnect
    LIMITED_ROLE="$(curl -sf --max-time 30 -X POST "$BASE_URL/api/v1/roles" -H "$AUTH" \
        -H 'Content-Type: application/json' \
        -d "{\"name\":\"smoke_limited_${SUFFIX}\",\"permission_codes\":[\"subscribers:read\"]}")"
    LIMITED_ROLE_ID="$(printf '%s' "$LIMITED_ROLE" | jq -r '.id')"
    LIMITED_USER="smoke_limited_${SUFFIX}"
    curl -s --max-time 30 -o /dev/null -X POST "$BASE_URL/api/v1/admins" -H "$AUTH" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$LIMITED_USER\",\"email\":\"$LIMITED_USER@netgrid.local\",\"password\":\"secret123\",\"role_ids\":[$LIMITED_ROLE_ID]}"
    LIMITED_TOKEN="$(curl -sf --max-time 30 -X POST "$BASE_URL/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$LIMITED_USER\",\"password\":\"secret123\"}" | jq -r '.access_token')"
    CODE="$(http_code "$BASE_URL/api/v1/sessions" -H "Authorization: Bearer $LIMITED_TOKEN")"
    check "limited admin denied on list (403)" "403" "$CODE"
    CODE="$(http_code -X POST "$BASE_URL/api/v1/sessions/1/disconnect" -H "Authorization: Bearer $LIMITED_TOKEN")"
    check "limited admin denied on disconnect (403)" "403" "$CODE"

    # --- cleanup admins/roles ---------------------------------------------------
    ADMIN_IDS="$(curl -sf --max-time 30 "$BASE_URL/api/v1/admins?page_size=100" -H "$AUTH" \
        | jq -r --arg a "$AUDITOR_USER" --arg l "$LIMITED_USER" \
            '.items[] | select(.username == $a or .username == $l) | .id')"
    for admin_id in $ADMIN_IDS; do
        curl -s --max-time 30 -o /dev/null -X DELETE "$BASE_URL/api/v1/admins/$admin_id" -H "$AUTH" || true
    done
    curl -s --max-time 30 -o /dev/null -X DELETE "$BASE_URL/api/v1/roles/$LIMITED_ROLE_ID" -H "$AUTH" || true
    echo "cleanup: smoke admins + role removed"
fi

# --- result -------------------------------------------------------------------
echo
echo "== result ===================================================================="
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ]
