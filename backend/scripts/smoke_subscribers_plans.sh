#!/usr/bin/env bash
#
# smoke_subscribers_plans.sh — curl-based smoke test for the NetGrid
# subscribers + plans APIs.
#
# Walks the subscriber/plan surface end to end against a running backend:
#   login -> create plan -> plan list/detail/patch -> create subscriber ->
#   subscriber stats/list/detail/history/sessions -> patch (status, plan
#   switch, password) -> delete -> error paths (404 / 409 / 422).
#
# The RADIUS coupling (radcheck/radgroupreply/radusergroup writes) is
# covered by the pytest integration suite; this script stays API-only.
# Assertions are scoped to the resources this run creates (unique names),
# so a shared dev DB with other data does not break it — except the
# subscriber-stats delta checks, which compare before/after our own create.
#
# Prerequisites: curl + jq on PATH; backend reachable at $BASE_URL;
# seeded admin exists (superadmin / netgrid-admin by default).
#
# Usage:
#   BASE_URL=http://localhost:8000 ./smoke_subscribers_plans.sh
#
# Exit code 0 = every check passed; 1 = one or more failed.
#
# Note: login is rate-limited to 5/min/IP, so don't run this in a tight loop.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-superadmin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-netgrid-admin}"

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

http_code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

# --- login ----------------------------------------------------------------
echo "== login ==================================================================="
LOGIN_JSON="$(curl -sf -X POST "$BASE_URL/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")" \
    || { echo "FAIL  login (is the backend up at $BASE_URL?)"; exit 1; }
TOKEN="$(printf '%s' "$LOGIN_JSON" | jq -r '.access_token')"
[ -n "$TOKEN" ] && token_state=non-empty || token_state=empty
check "login issues access token" "non-empty" "$token_state"
AUTH="Authorization: Bearer $TOKEN"

# Unique names so a re-run (or a same-second run after smoke_invoices.sh in
# CI) never collides with leftovers from a previous run. The sub_ prefix
# keeps this script's resources out of smoke_invoices.sh's namespace.
SUFFIX="$(date +%s)_$RANDOM"
PLAN_NAME="subsmoke_${SUFFIX}"
RADIUS_GROUP="rad_subsmoke_${SUFFIX}"
PLAN2_NAME="subsmoke2_${SUFFIX}"
RADIUS_GROUP2="rad_subsmoke2_${SUFFIX}"
SUB_USERNAME="subsmoke_${SUFFIX}"

# --- plans -----------------------------------------------------------------
echo "== plans ====================================================================="
PLAN="$(curl -sf -X POST "$BASE_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$PLAN_NAME\",\"radius_group\":\"$RADIUS_GROUP\",\"price\":\"9.99\",\"duration_days\":30,\"bandwidth_down_mbps\":10,\"bandwidth_up_mbps\":5,\"quota_gb\":100}")"
PLAN_ID="$(printf '%s' "$PLAN" | jq -r '.id')"
check "plan created" "non-empty" "$([ -n "$PLAN_ID" ] && [ "$PLAN_ID" != "null" ] && echo non-empty || echo empty)"
check "plan price" "9.99" "$(printf '%s' "$PLAN" | jq -r '.price')"
check "plan duration" "30" "$(printf '%s' "$PLAN" | jq -r '.duration_days')"
check "plan quota" "100" "$(printf '%s' "$PLAN" | jq -r '.quota_gb')"
check "plan active" "true" "$(printf '%s' "$PLAN" | jq -r '.is_active')"
check "plan subscriber_count starts at 0" "0" "$(printf '%s' "$PLAN" | jq -r '.subscriber_count')"

PLAN2="$(curl -sf -X POST "$BASE_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$PLAN2_NAME\",\"radius_group\":\"$RADIUS_GROUP2\",\"price\":\"19.99\",\"duration_days\":60,\"bandwidth_down_mbps\":50,\"bandwidth_up_mbps\":20}")"
PLAN2_ID="$(printf '%s' "$PLAN2" | jq -r '.id')"
check "second plan created" "non-empty" "$([ -n "$PLAN2_ID" ] && [ "$PLAN2_ID" != "null" ] && echo non-empty || echo empty)"

LIST="$(curl -sf "$BASE_URL/api/v1/plans" -H "$AUTH")"
check "plan list includes ours" "true" \
    "$(printf '%s' "$LIST" | jq -r --arg n "$PLAN_NAME" '.items | any(.name == $n)')"

DETAIL="$(curl -sf "$BASE_URL/api/v1/plans/$PLAN_ID" -H "$AUTH")"
check "plan detail matches id" "$PLAN_ID" "$(printf '%s' "$DETAIL" | jq -r '.id')"

PATCHED="$(curl -sf -X PATCH "$BASE_URL/api/v1/plans/$PLAN_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"bandwidth_down_mbps":20}')"
check "plan patch updates bandwidth" "20" "$(printf '%s' "$PATCHED" | jq -r '.bandwidth_down_mbps')"

# --- subscribers ------------------------------------------------------------
echo "== subscribers ================================================================"
# capture stats before creating, so the delta checks survive a shared dev DB
STATS_BEFORE="$(curl -sf "$BASE_URL/api/v1/subscribers/stats" -H "$AUTH")"
ACTIVE_BEFORE="$(printf '%s' "$STATS_BEFORE" | jq -r '.active')"
TOTAL_BEFORE="$(printf '%s' "$STATS_BEFORE" | jq -r '.total')"

SUB="$(curl -sf -X POST "$BASE_URL/api/v1/subscribers" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$SUB_USERNAME\",\"full_name\":\"Smoke Test\",\"email\":\"$SUB_USERNAME@netgrid.local\",\"password\":\"radpass123\",\"plan_id\":$PLAN_ID}")"
SUB_ID="$(printf '%s' "$SUB" | jq -r '.id')"
check "subscriber created" "non-empty" "$([ -n "$SUB_ID" ] && [ "$SUB_ID" != "null" ] && echo non-empty || echo empty)"
check "subscriber status defaults active" "active" "$(printf '%s' "$SUB" | jq -r '.status')"
check "subscriber on plan" "$PLAN_ID" "$(printf '%s' "$SUB" | jq -r '.plan_id')"
check "subscriber full_name" "Smoke Test" "$(printf '%s' "$SUB" | jq -r '.full_name')"

STATS_AFTER="$(curl -sf "$BASE_URL/api/v1/subscribers/stats" -H "$AUTH")"
check "stats active +1" "$((ACTIVE_BEFORE + 1))" "$(printf '%s' "$STATS_AFTER" | jq -r '.active')"
check "stats total +1" "$((TOTAL_BEFORE + 1))" "$(printf '%s' "$STATS_AFTER" | jq -r '.total')"
check "stats by_plan shows ours at 1" "1" \
    "$(printf '%s' "$STATS_AFTER" | jq -r --argjson pid "$PLAN_ID" '.by_plan[] | select(.plan_id == $pid) | .count')"

LIST="$(curl -sf "$BASE_URL/api/v1/subscribers" -H "$AUTH")"
check "subscriber list finds ours" "$SUB_USERNAME" \
    "$(printf '%s' "$LIST" | jq -r --arg u "$SUB_USERNAME" '.items[] | select(.username == $u) | .username')"

SEARCH="$(curl -sf "$BASE_URL/api/v1/subscribers?q=$SUB_USERNAME" -H "$AUTH")"
check "subscriber search narrows to ours" "1" "$(printf '%s' "$SEARCH" | jq -r '.total')"

DETAIL="$(curl -sf "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH")"
check "subscriber detail" "$SUB_USERNAME" "$(printf '%s' "$DETAIL" | jq -r '.username')"

HISTORY="$(curl -sf "$BASE_URL/api/v1/subscribers/$SUB_ID/history" -H "$AUTH")"
check "history records the create" "create" "$(printf '%s' "$HISTORY" | jq -r '.[0].action')"

SESSIONS="$(curl -sf "$BASE_URL/api/v1/subscribers/$SUB_ID/sessions" -H "$AUTH")"
check "no live sessions yet" "0" "$(printf '%s' "$SESSIONS" | jq -r 'length')"

# --- subscriber patches ------------------------------------------------------
echo "== subscriber patches ============================================================"
PATCHED="$(curl -sf -X PATCH "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"full_name":"Smoke Renamed","status":"suspended"}')"
check "patch renames subscriber" "Smoke Renamed" "$(printf '%s' "$PATCHED" | jq -r '.full_name')"
check "patch suspends subscriber" "suspended" "$(printf '%s' "$PATCHED" | jq -r '.status')"

STATS_SUSPENDED="$(curl -sf "$BASE_URL/api/v1/subscribers/stats" -H "$AUTH")"
check "stats active back to before" "$ACTIVE_BEFORE" \
    "$(printf '%s' "$STATS_SUSPENDED" | jq -r '.active')"
check "stats suspended +1" "$(( $(printf '%s' "$STATS_BEFORE" | jq -r '.suspended') + 1 ))" \
    "$(printf '%s' "$STATS_SUSPENDED" | jq -r '.suspended')"

PATCHED="$(curl -sf -X PATCH "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d "{\"plan_id\":$PLAN2_ID,\"status\":\"active\"}")"
check "patch switches plan" "$PLAN2_ID" "$(printf '%s' "$PATCHED" | jq -r '.plan_id')"
check "patch reactivates" "active" "$(printf '%s' "$PATCHED" | jq -r '.status')"

CODE="$(http_code -X PATCH "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"password":"newpass456"}')"
check "password-only patch returns 200" "200" "$CODE"

PLAN1_NOW="$(curl -sf "$BASE_URL/api/v1/plans/$PLAN_ID" -H "$AUTH")"
PLAN2_NOW="$(curl -sf "$BASE_URL/api/v1/plans/$PLAN2_ID" -H "$AUTH")"
check "plan1 count back to 0 after switch" "0" "$(printf '%s' "$PLAN1_NOW" | jq -r '.subscriber_count')"
check "plan2 count 1 after switch" "1" "$(printf '%s' "$PLAN2_NOW" | jq -r '.subscriber_count')"

HISTORY="$(curl -sf "$BASE_URL/api/v1/subscribers/$SUB_ID/history" -H "$AUTH")"
# newest event with status metadata first — the password-only patch also
# created an update event, but it carries no status_from/status_to
STATUS_EVENT="$(printf '%s' "$HISTORY" | jq -c '[.[] | select(.metadata_.status_from != null)][0]')"
check "history records a status transition" "update" "$(printf '%s' "$STATUS_EVENT" | jq -r '.action')"
# the last status-bearing patch went suspended -> active
check "history status_from is suspended" "suspended" "$(printf '%s' "$STATUS_EVENT" | jq -r '.metadata_.status_from')"
check "history status_to is active" "active" "$(printf '%s' "$STATUS_EVENT" | jq -r '.metadata_.status_to')"

# --- error paths --------------------------------------------------------------
echo "== error paths =================================================================="
CODE="$(http_code -X POST "$BASE_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$PLAN_NAME\",\"radius_group\":\"rad_other_${SUFFIX}\",\"price\":\"1.00\",\"duration_days\":30,\"bandwidth_down_mbps\":1,\"bandwidth_up_mbps\":1}")"
check "409 duplicate plan name" "409" "$CODE"
CODE="$(http_code -X POST "$BASE_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"other_${SUFFIX}\",\"radius_group\":\"$RADIUS_GROUP\",\"price\":\"1.00\",\"duration_days\":30,\"bandwidth_down_mbps\":1,\"bandwidth_up_mbps\":1}")"
check "409 duplicate radius_group" "409" "$CODE"
CODE="$(http_code -X POST "$BASE_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"bad_${SUFFIX}\",\"radius_group\":\"rad_bad_${SUFFIX}\",\"price\":\"1.00\",\"duration_days\":0,\"bandwidth_down_mbps\":1,\"bandwidth_up_mbps\":1}")"
check "422 invalid plan payload" "422" "$CODE"
CODE="$(http_code "$BASE_URL/api/v1/plans/999999" -H "$AUTH")"
check "404 unknown plan" "404" "$CODE"

CODE="$(http_code -X POST "$BASE_URL/api/v1/subscribers" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$SUB_USERNAME\",\"full_name\":\"Dup\",\"password\":\"radpass123\"}")"
check "409 duplicate subscriber username" "409" "$CODE"
CODE="$(http_code -X POST "$BASE_URL/api/v1/subscribers" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"bad_${SUFFIX}\",\"full_name\":\"Bad\",\"password\":\"radpass123\",\"status\":\"frozen\"}")"
check "422 invalid subscriber status" "422" "$CODE"
CODE="$(http_code "$BASE_URL/api/v1/subscribers/999999" -H "$AUTH")"
check "404 unknown subscriber" "404" "$CODE"
CODE="$(http_code -X PATCH "$BASE_URL/api/v1/subscribers/999999" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"full_name":"X"}')"
check "404 patch unknown subscriber" "404" "$CODE"

# --- delete ---------------------------------------------------------------------
echo "== delete ======================================================================"
CODE="$(http_code -X DELETE "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH")"
check "204 delete subscriber" "204" "$CODE"
CODE="$(http_code "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH")"
check "404 after delete" "404" "$CODE"
PLAN1_NOW="$(curl -sf "$BASE_URL/api/v1/plans/$PLAN_ID" -H "$AUTH")"
check "plan counts return to 0" "0" "$(printf '%s' "$PLAN1_NOW" | jq -r '.subscriber_count')"

# --- cleanup (best-effort, so a re-run starts from a clean slate) -----------
# Plans have no DELETE endpoint — decommissioning means is_active=false.
echo "== cleanup ======================================================================"
for pid in "$PLAN_ID" "$PLAN2_ID"; do
    curl -s -o /dev/null -X PATCH "$BASE_URL/api/v1/plans/$pid" -H "$AUTH" \
        -H 'Content-Type: application/json' -d '{"is_active":false}' || true
done
echo "cleanup done (plans deactivated)"

# --- result -------------------------------------------------------------------
echo
echo "== result ===================================================================="
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ]
