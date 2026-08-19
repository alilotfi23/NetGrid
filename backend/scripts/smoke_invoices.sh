#!/usr/bin/env bash
#
# smoke_invoices.sh — curl-based smoke test for the NetGrid invoices API.
#
# Walks the whole billing flow end to end against a running backend:
#   login -> create plan -> create subscriber -> generate invoices ->
#   list/detail -> partial + full payment (paid transition) -> revenue
#   report -> status filter -> error paths (404 / 409 / 422).
#
# Prerequisites: curl + jq on PATH; backend reachable at $BASE_URL;
# seeded admin exists (superadmin / netgrid-admin by default).
#
# The "empty state" checks assume a clean invoices table (fresh dev DB or
# after the script's own cleanup). Runs are self-cleaning, so re-running
# against the same DB is safe.
#
# Usage:
#   BASE_URL=http://localhost:8000 ./smoke_invoices.sh
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
echo "== login =="
LOGIN_JSON="$(curl -sf -X POST "$BASE_URL/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}")" \
    || { echo "FAIL  login (is the backend up at $BASE_URL?)"; exit 1; }
TOKEN="$(printf '%s' "$LOGIN_JSON" | jq -r '.access_token')"
[ -n "$TOKEN" ] && token_state=non-empty || token_state=empty
check "login issues access token" "non-empty" "$token_state"
AUTH="Authorization: Bearer $TOKEN"

# Unique names so a re-run never collides with leftovers from a previous run.
SUFFIX="$(date +%s)"
PLAN_NAME="smoke_${SUFFIX}"
RADIUS_GROUP="rad_smoke_${SUFFIX}"
SUB_USERNAME="smoke_${SUFFIX}"

# --- empty state ----------------------------------------------------------
echo "== empty state =="
LIST="$(curl -sf "$BASE_URL/api/v1/invoices" -H "$AUTH")"
check "invoices list returns 0 items" "0" "$(printf '%s' "$LIST" | jq -r '.total')"
check "stats all zero" '{"issued":0,"paid":0,"overdue":0}' \
    "$(printf '%s' "$LIST" | jq -c '.stats | {issued, paid, overdue}')"

# --- setup: plan + subscriber --------------------------------------------
echo "== setup (plan + subscriber) =="
PLAN="$(curl -sf -X POST "$BASE_URL/api/v1/plans" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$PLAN_NAME\",\"radius_group\":\"$RADIUS_GROUP\",\"price\":\"10.00\",\"duration_days\":30,\"bandwidth_down_mbps\":10,\"bandwidth_up_mbps\":5}")"
PLAN_ID="$(printf '%s' "$PLAN" | jq -r '.id')"
check "plan created with price" "10.00" "$(printf '%s' "$PLAN" | jq -r '.price')"

SUB="$(curl -sf -X POST "$BASE_URL/api/v1/subscribers" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$SUB_USERNAME\",\"full_name\":\"Smoke Test\",\"password\":\"radpass123\",\"plan_id\":$PLAN_ID}")"
SUB_ID="$(printf '%s' "$SUB" | jq -r '.id')"
check "subscriber created on plan" "$PLAN_ID" "$(printf '%s' "$SUB" | jq -r '.plan_id')"

# --- generate -------------------------------------------------------------
echo "== invoice generation =="
GEN="$(curl -sf -X POST "$BASE_URL/api/v1/invoices/generate" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{}')"
check "generate creates 1 invoice" "1" "$(printf '%s' "$GEN" | jq -r '.created')"

GEN2="$(curl -sf -X POST "$BASE_URL/api/v1/invoices/generate" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{}')"
check "generate is idempotent on re-run" "0" "$(printf '%s' "$GEN2" | jq -r '.created')"

# --- list + detail --------------------------------------------------------
echo "== list + detail =="
LIST="$(curl -sf "$BASE_URL/api/v1/invoices" -H "$AUTH")"
INVOICE_ID="$(printf '%s' "$LIST" \
    | jq -r --arg sub "$SUB_USERNAME" '.items[] | select(.subscriber_username == $sub) | .id')"
check "invoice listed for subscriber" "non-empty" "$([ -n "$INVOICE_ID" ] && echo non-empty || echo empty)"
check "invoice amount" "10.00" "$(printf '%s' "$LIST" | jq -r --arg id "$INVOICE_ID" '.items[] | select(.id == ($id|tonumber)) | .amount')"
check "invoice status issued" "issued" "$(printf '%s' "$LIST" | jq -r --arg id "$INVOICE_ID" '.items[] | select(.id == ($id|tonumber)) | .status')"
check "invoice has plan name" "$PLAN_NAME" "$(printf '%s' "$LIST" | jq -r --arg id "$INVOICE_ID" '.items[] | select(.id == ($id|tonumber)) | .plan_name')"

DETAIL="$(curl -sf "$BASE_URL/api/v1/invoices/$INVOICE_ID" -H "$AUTH")"
check "detail status" "issued" "$(printf '%s' "$DETAIL" | jq -r '.status')"
check "detail has no payments yet" "0" "$(printf '%s' "$DETAIL" | jq -r '.payments | length')"
check "detail resolves username" "$SUB_USERNAME" "$(printf '%s' "$DETAIL" | jq -r '.subscriber_username')"

# --- payments -------------------------------------------------------------
echo "== payments =="
PAY1="$(curl -sf -X POST "$BASE_URL/api/v1/invoices/$INVOICE_ID/payments" -H "$AUTH" \
    -H 'Content-Type: application/json' \
    -d '{"amount":"6.00","method":"bank_transfer","reference":"smoke-1"}')"
check "partial payment recorded" "completed" "$(printf '%s' "$PAY1" | jq -r '.payment.status')"
check "partial payment keeps invoice issued" "issued" "$(printf '%s' "$PAY1" | jq -r '.invoice.status')"

PAY2="$(curl -sf -X POST "$BASE_URL/api/v1/invoices/$INVOICE_ID/payments" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"amount":"4.00","method":"cash"}')"
check "second payment completes invoice" "paid" "$(printf '%s' "$PAY2" | jq -r '.invoice.status')"
check "paid_at is set" "true" "$(printf '%s' "$PAY2" | jq -r '.invoice.paid_at != null')"

DETAIL="$(curl -sf "$BASE_URL/api/v1/invoices/$INVOICE_ID" -H "$AUTH")"
check "detail now shows 2 payments" "2" "$(printf '%s' "$DETAIL" | jq -r '.payments | length')"

LIST="$(curl -sf "$BASE_URL/api/v1/invoices" -H "$AUTH")"
check "stats count one paid" '{"issued":0,"paid":1,"overdue":0}' \
    "$(printf '%s' "$LIST" | jq -c '.stats | {issued, paid, overdue}')"
check "nothing outstanding" "0.00" "$(printf '%s' "$LIST" | jq -r '.stats.outstanding_amount')"

# --- revenue report -------------------------------------------------------
echo "== revenue report =="
REPORT="$(curl -sf "$BASE_URL/api/v1/invoices/report" -H "$AUTH")"
# The report is global, so assert *our* buckets exist rather than exact totals
# (a shared dev DB may hold payments from other runs).
check "report has our cash bucket" "true" \
    "$(printf '%s' "$REPORT" | jq -r '.items | any(.method == "cash" and .revenue == "4.00")')"
check "report has our bank_transfer bucket" "true" \
    "$(printf '%s' "$REPORT" | jq -r '.items | any(.method == "bank_transfer" and .revenue == "6.00")')"
check "report total covers our payments" "true" \
    "$(printf '%s' "$REPORT" | jq -r '.total_revenue | tonumber >= 10.0')"
check "report includes current month" "true" \
    "$(printf '%s' "$REPORT" | jq -r --arg m "$(date +%Y-%m)" '.items | any(.month == $m)')"

# --- error paths ----------------------------------------------------------
echo "== error paths =="
CODE="$(http_code "$BASE_URL/api/v1/invoices/999999" -H "$AUTH")"
check "404 unknown invoice" "404" "$CODE"

CODE="$(http_code -X POST "$BASE_URL/api/v1/invoices/$INVOICE_ID/payments" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"amount":"1.00","method":"cash"}')"
check "409 paying an already-paid invoice" "409" "$CODE"

CODE="$(http_code -X POST "$BASE_URL/api/v1/invoices/999999/payments" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"amount":"1.00","method":"cash"}')"
check "404 payment on unknown invoice" "404" "$CODE"

CODE="$(http_code -X POST "$BASE_URL/api/v1/invoices/1/payments" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"amount":"-5.00","method":"cash"}')"
check "422 negative payment amount" "422" "$CODE"

CODE="$(http_code "$BASE_URL/api/v1/invoices?status=bogus" -H "$AUTH")"
check "422 invalid status filter" "422" "$CODE"

CODE="$(http_code "$BASE_URL/api/v1/invoices/report?year=1999" -H "$AUTH")"
check "422 year out of range" "422" "$CODE"

# --- cleanup (best-effort, so a re-run starts from a clean slate) ---------
# Deleting the subscriber cascades to its invoices and payments; deactivating
# the plan stops future generations from billing it.
echo "== cleanup ==================================================================="
curl -s -o /dev/null -X DELETE "$BASE_URL/api/v1/subscribers/$SUB_ID" -H "$AUTH" || true
curl -s -o /dev/null -X PATCH "$BASE_URL/api/v1/plans/$PLAN_ID" -H "$AUTH" \
    -H 'Content-Type: application/json' -d '{"is_active":false}' || true
echo "cleanup done (subscriber deleted, plan deactivated)"

# --- result ---------------------------------------------------------------
echo
echo "== result ==================================================================="
echo "passed: $pass   failed: $fail"
[ "$fail" -eq 0 ]
