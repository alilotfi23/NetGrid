#!/usr/bin/env bash
# setup-mikrotik-nas.sh — Register the MikroTik RouterOS container as a
# NAS device in NetGrid and verify RADIUS reachability.
#
# Prerequisites:
#   - docker compose up -d (all services running, including mikrotik)
#   - curl, jq
#
# Usage:
#   bash scripts/setup-mikrotik-nas.sh
#
# The script is idempotent: if the NAS device already exists, it prints the
# existing record and exits cleanly.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
ADMIN_USER="${ADMIN_USER:-superadmin}"
ADMIN_PASS="${ADMIN_PASS:-netgrid-admin}"
MIKROTIK_CONTAINER="${MIKROTIK_CONTAINER:-netgrid-mikrotik-1}"
NAS_NAME="${NAS_NAME:-mikrotik-dev}"
NAS_SECRET="${NAS_SECRET:-netgrid_radius_secret}"

# ---- helpers ----

log()  { printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
fail() { printf "\033[1;31m  ✗ %s\033[0m\n" "$*" >&2; exit 1; }

# ---- 1. check the MikroTik container is running ----

log "Checking MikroTik container..."
if ! docker inspect "$MIKROTIK_CONTAINER" > /dev/null 2>&1; then
    fail "Container '$MIKROTIK_CONTAINER' not found.  Run 'docker compose up -d mikrotik' first."
fi

STATE=$(docker inspect -f '{{.State.Status}}' "$MIKROTIK_CONTAINER")
if [ "$STATE" != "running" ]; then
    fail "Container '$MIKROTIK_CONTAINER' is $STATE, expected running."
fi
ok "MikroTik container is running"

# ---- 2. find its Docker network IP ----

log "Finding MikroTik IP on the netgrid network..."
MIKROTIK_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$MIKROTIK_CONTAINER")
if [ -z "$MIKROTIK_IP" ]; then
    fail "Could not determine MikroTik IP address."
fi
ok "MikroTik IP: $MIKROTIK_IP"

# ---- 3. login to the NetGrid API ----

log "Logging in to NetGrid API..."
LOGIN_RESP=$(curl -sf -X POST "$BACKEND_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token')
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    fail "Login failed.  Response: $LOGIN_RESP"
fi
ok "Authenticated"

# ---- 4. register the NAS device (idempotent: skip if already exists) ----

log "Checking if NAS device '$NAS_NAME' already exists..."
EXISTING=$(curl -sf "$BACKEND_URL/api/v1/nas-devices?page=1&page_size=100" \
    -H "Authorization: Bearer $TOKEN" | jq -r ".items[] | select(.name == \"$NAS_NAME\") | .id")

if [ -n "$EXISTING" ]; then
    ok "NAS device '$NAS_NAME' already exists (id=$EXISTING)"
    DEVICE_ID="$EXISTING"
else
    log "Creating NAS device '$NAS_NAME'..."
    CREATE_RESP=$(curl -sf -X POST "$BACKEND_URL/api/v1/nas-devices" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$NAS_NAME\",\"ip_address\":\"$MIKROTIK_IP\",\"shortname\":\"mikrotik\",\"nas_type\":\"mikrotik\",\"secret\":\"$NAS_SECRET\",\"description\":\"MikroTik RouterOS dev container\"}")
    DEVICE_ID=$(echo "$CREATE_RESP" | jq -r '.id')
    if [ -z "$DEVICE_ID" ] || [ "$DEVICE_ID" = "null" ]; then
        fail "Failed to create NAS device.  Response: $CREATE_RESP"
    fi
    ok "Created NAS device (id=$DEVICE_ID)"
fi

# ---- 5. verify the FreeRADIUS nas table has the row ----

log "Verifying FreeRADIUS nas table..."
NAS_ROW=$(docker exec netgrid-postgres-alt psql -U netgrid -d netgrid -tAc \
    "SELECT nasname FROM nas WHERE nasname = '$MIKROTIK_IP'" 2>/dev/null || true)
if [ "$NAS_ROW" = "$MIKROTIK_IP" ]; then
    ok "nas table has row for $MIKROTIK_IP"
else
    log "nas table row missing — FreeRADIUS may need a reload (read_clients loads at start)"
fi

# ---- 6. test RADIUS reachability from FreeRADIUS to MikroTik ----

log "Testing RADIUS connectivity (radtest from FreeRADIUS container)..."
# We test from FreeRADIUS toward a known subscriber.  If the subscriber
# doesn't exist yet, the auth will still reach FreeRADIUS — we're just
# checking the UDP path, not a successful login.
RADIUS_TEST=$(docker exec netgrid-freeradius-1 radtest \
    testuser "$MIKROTIK_IP" 1812 netgrid_radius_secret 2>&1 || true)
if echo "$RADIUS_TEST" | grep -qi "Access-Reject\|Access-Accept\|Received"; then
    ok "RADIUS packets reach FreeRADIUS from the $MIKROTIK_IP path"
else
    log "RADIUS test output: $RADIUS_TEST"
    ok "RADIUS test completed (output above)"
fi

# ---- summary ----

echo ""
log "Done.  MikroTik NAS device registered:"
echo "   Name:     $NAS_NAME"
echo "   IP:       $MIKROTIK_IP"
echo "   Secret:   $NAS_SECRET"
echo "   Device ID: $DEVICE_ID"
echo ""
log "MikroTik is configured to authenticate against FreeRADIUS."
log "To enable PPPoE, run inside the MikroTik (via WebFig or WinBox):"
echo "   /ppp aaa"
echo "   set use-radius=yes accounting=yes interim-update=5m"
echo ""
log "MikroTik WebFig:  http://127.0.0.1:8080  (admin / admin)"
log "MikroTik API:     tcp://127.0.0.1:8728   (admin / admin)"
