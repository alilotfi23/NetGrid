#!/bin/sh
# sim-nas entrypoint: prove the RFC 5176 packet math at boot, then run the
# CoA responder (UDP 3799) alongside the Access-Request client. The client
# runs in the foreground so Docker tracks the "primary" process; the
# responder is a daemon thread-equivalent background process reaped on exit.
set -e

echo "[sim-nas] running CoA packet self-test..."
python3 /coa_server.py --selftest

echo "[sim-nas] starting CoA responder (UDP 3799)..."
python3 /coa_server.py &
COA_PID=$!

echo "[sim-nas] starting RADIUS Access-Request client..."
python3 /nas_client.py
status=$?

kill "$COA_PID" 2>/dev/null || true
exit "$status"
