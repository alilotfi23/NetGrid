#!/usr/bin/env bash
#
# smoke_e2e.sh — full-stack end-to-end smoke test via `docker compose up`.
#
# Brings up the entire stack exactly the way the README quickstart says to
# run it — postgres, redis, freeradius, backend, frontend — and proves the
# pieces interoperate over the compose network:
#
#   1. all five services reach healthy, with the backend auto-migrating on
#      startup (no host-side `alembic upgrade head` step)
#   2. the frontend serves pages and reaches the API through the compose
#      network (BACKEND_URL=http://backend:8000)
#   3. an admin can log in through the compose backend container
#   4. a subscriber created through the API can authenticate through
#      FreeRADIUS — the direct radcheck coupling, proven cross-process
#   5. suspending the subscriber through the API makes FreeRADIUS reject
#      them immediately (status -> Auth-Type Reject propagation)
#   6. the three API smoke scripts (backend/scripts) pass against the
#      compose backend container
#
# The script leaves the stack running on success so you can poke at it; CI
# tears it down (see .github/workflows/nightly.yml). Re-runs are safe:
# everything created here is deleted before exit, and the smoke scripts are
# self-cleaning. Note the API smoke scripts make five logins between them and
# login is rate-limited to 5/min/IP — this script paces its own logins (60s
# before the smoke phase) so the combined total stays legal.
#
# Prerequisites: docker compose v2; ports 5432/6379/1812/1813/8000/3000 free.
#
# Usage:
#   ./scripts/smoke_e2e.sh
#
# Exit code 0 = every check passed; 1 = one or more failed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-superadmin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-netgrid-admin}"
# The localhost client in freeradius/raddb/clients.conf (used by radtest).
RADIUS_SECRET="${RADIUS_SECRET:-testing123}"

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

http_code() { curl -s --max-time 30 -o /dev/null -w '%{http_code}' "$@"; }

psql_value() { docker compose exec -T postgres psql -U netgrid -d netgrid -tAc "$1"; }

# --- 1. full stack up -------------------------------------------------------
echo "== docker compose up (full stack) ============================================="
docker compose up -d --wait

# --- 2. health ---------------------------------------------------------------
echo "== health ======================================================================"
# compose --wait already gates on the healthchecks; re-poll as a guard so the
# failures below have useful context rather than a curl connection error.
BACKEND_OK="no"
for _ in $(seq 1 30); do
    if curl -sf "$BACKEND_URL/api/v1/health" >/dev/null 2>&1; then
        BACKEND_OK="yes"
        break
    fi
    sleep 2
done
check "backend health endpoint" "yes" "$BACKEND_OK"
if [ "$BACKEND_OK" != "yes" ]; then
    echo "--- backend container log (tail) ---"
    docker compose logs --tail=50 backend || true
fi

CODE="$(http_code "$FRONTEND_URL/login")"
check "frontend serves HTTP 200" "200" "$CODE"
BODY="$(curl -sf "$FRONTEND_URL/login")"
check "frontend renders the login page" "true" \
    "$(printf '%s' "$BODY" | grep -qi 'NetGrid' && echo true || echo false)"

# --- 3. admin login through the compose backend ------------------------------
echo "== admin login =================================================================="
LOGIN_JSON="$(curl -sf --max-time 30 -X POST "$BACKEND_URL/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")" \
    || { echo "FAIL  login (did the seed migration run? the backend auto-migrates on start)"; exit 1; }
TOKEN="$(printf '%s' "$LOGIN_JSON" | jq -r '.access_token')"
check "login issues access token" "non-empty" "$([ -n "$TOKEN" ] && echo non-empty || echo empty)"
AUTH="Authorization: Bearer $TOKEN"

# --- 4. subscriber -> FreeRADIUS round trip -----------------------------------
echo "== subscriber -> FreeRADIUS round trip =========================================="
SUFFIX="$(date +%s)"
E2E_USER="e2e_${SUFFIX}"
PLAN_NAME="e2e_plan_${SUFFIX}"
RADIUS_GROUP="rad_e2e_${SUFFIX}"

PLAN="$(curl -sf --max-time 30 -X POST "$BACKEND_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$PLAN_NAME\",\"radius_group\":\"$RADIUS_GROUP\",\"price\":\"10.00\",\"duration_days\":30,\"bandwidth_down_mbps\":10,\"bandwidth_up_mbps\":5}")"
PLAN_ID="$(printf '%s' "$PLAN" | jq -r '.id')"
check "plan created" "non-empty" "$([ -n "$PLAN_ID" ] && [ "$PLAN_ID" != "null" ] && echo non-empty || echo empty)"

SUB="$(curl -sf --max-time 30 -X POST "$BACKEND_URL/api/v1/subscribers" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$E2E_USER\",\"full_name\":\"E2E Smoke\",\"password\":\"radpass123\",\"plan_id\":$PLAN_ID}")"
SUB_ID="$(printf '%s' "$SUB" | jq -r '.id')"
check "subscriber created through API" "non-empty" \
    "$([ -n "$SUB_ID" ] && [ "$SUB_ID" != "null" ] && echo non-empty || echo empty)"

# the API must have written FreeRADIUS's auth rows in the same transaction
RCHECKS="$(psql_value "SELECT count(*) FROM radcheck WHERE username='$E2E_USER' AND attribute='Cleartext-Password'")"
check "API wrote radcheck Cleartext-Password" "1" "$RCHECKS"
RGROUPS="$(psql_value "SELECT count(*) FROM radusergroup WHERE username='$E2E_USER'")"
check "API wrote radusergroup assignment" "1" "$RGROUPS"

# FreeRADIUS needs a moment after the container starts; retry until it answers.
RAD_OUT=""
for _ in 1 2 3 4 5; do
    RAD_OUT="$(docker compose exec -T freeradius radtest "$E2E_USER" radpass123 127.0.0.1 0 "$RADIUS_SECRET" 2>&1 || true)"
    if printf '%s' "$RAD_OUT" | grep -q "Received"; then
        break
    fi
    sleep 2
done
check "FreeRADIUS accepts active subscriber" "true" \
    "$(printf '%s' "$RAD_OUT" | grep -q 'Access-Accept' && echo true || echo false)"

# --- 5. suspend -> reject -----------------------------------------------------
echo "== suspend propagation =========================================================="
curl -sf --max-time 30 -X PATCH "$BACKEND_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"status":"suspended"}' >/dev/null
RAD_OUT="$(docker compose exec -T freeradius radtest "$E2E_USER" radpass123 127.0.0.1 0 "$RADIUS_SECRET" 2>&1 || true)"
check "FreeRADIUS rejects suspended subscriber" "true" \
    "$(printf '%s' "$RAD_OUT" | grep -q 'Access-Reject' && echo true || echo false)"
# the rejection was logged for the lockout policy to count
POSTAUTH="$(psql_value "SELECT count(*) FROM radpostauth WHERE username='$E2E_USER' AND reply='Access-Reject'")"
check "rejection logged to radpostauth" "1" "$POSTAUTH"

# --- 6. cleanup of the e2e resources ------------------------------------------
echo "== cleanup ======================================================================="
curl -s --max-time 30 -o /dev/null -X DELETE "$BACKEND_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH" || true
curl -s --max-time 30 -o /dev/null -X PATCH "$BACKEND_URL/api/v1/plans/$PLAN_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"is_active":false}' || true
psql_value "DELETE FROM radpostauth WHERE username='$E2E_USER';" >/dev/null || true
echo "cleanup done (subscriber deleted, plan deactivated, radpostauth rows cleared)"

# --- 7. API smoke scripts against the compose backend --------------------------
# The three scripts make five logins between them; login is 5/min/IP, so pace
# this script's own logins above out of the way first.
echo "== pacing 60s for the login rate-limit window ===================================="
sleep 60
echo "== API smoke scripts (against compose backend) =================================="
for script in smoke_invoices.sh smoke_subscribers_plans.sh smoke_sessions.sh; do
    if BASE_URL="$BACKEND_URL" ./backend/scripts/"$script"; then
        check "$script" "pass" "pass"
    else
        check "$script" "pass" "FAILED"
    fi
done

# --- result -------------------------------------------------------------------
echo
echo "== result ===================================================================="
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ]
