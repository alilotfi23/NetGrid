#!/usr/bin/env python3
"""Register a NAS device in NetGrid (sim-nas or MikroTik).

Detects the Docker container's IP on the netgrid network, logs in to the
NetGrid API, and creates the NAS device (idempotent — skips if it already
exists).  Also creates a test subscriber (demo-user / demo-pass) so the
sim-nas container can authenticate immediately.

Usage:
    python scripts/setup-mikrotik-nas.py
    python scripts/setup-mikrotik-nas.py --container netgrid-sim-nas-1
"""

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

BACKEND_URL = "http://127.0.0.1:8000"
ADMIN_USER = "superadmin"
ADMIN_PASS = "netgrid-admin"
DEFAULT_CONTAINER = "netgrid-sim-nas-1"
NAS_NAME = "sim-nas-dev"
NAS_SECRET = "netgrid_radius_secret"


def _api(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    """Make an API call and return the parsed JSON response."""
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BACKEND_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode()
        print(f"  API error {exc.code}: {err_body}", file=sys.stderr)
        sys.exit(1)


def docker_inspect(container: str, fmt: str) -> str:
    result = subprocess.run(
        ["docker", "inspect", "-f", fmt, container],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  docker inspect failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a NAS device in NetGrid")
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help="Docker container name")
    parser.add_argument("--nas-name", default=NAS_NAME, help="NAS device name in NetGrid")
    args = parser.parse_args()

    # 1. check container
    print("> Checking container...")
    state = docker_inspect(args.container, "{{.State.Status}}")
    if state != "running":
        print(f"  Container is {state}, expected running.", file=sys.stderr)
        sys.exit(1)
    print(f"  OK Container '{args.container}' is running")

    # 2. find IP
    print("> Finding IP on the netgrid network...")
    ip = docker_inspect(args.container, "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}")
    if not ip:
        print("  Could not determine container IP.", file=sys.stderr)
        sys.exit(1)
    print(f"  OK IP: {ip}")

    # 3. login
    print("> Logging in to NetGrid API...")
    login = _api(
        "POST",
        "/api/v1/auth/login",
        body={"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    token = login.get("access_token")
    if not token:
        print(f"  Login failed: {login}", file=sys.stderr)
        sys.exit(1)
    print("  OK Authenticated")

    # 4. check existing
    print(f"> Checking if NAS '{args.nas_name}' exists...")
    devices = _api("GET", "/api/v1/nas-devices?page=1&page_size=100", token=token)
    existing = [d for d in devices.get("items", []) if d["name"] == args.nas_name]

    if existing:
        device_id = existing[0]["id"]
        print(f"  OK Already exists (id={device_id})")
    else:
        print(f"> Creating NAS device '{args.nas_name}'...")
        result = _api(
            "POST",
            "/api/v1/nas-devices",
            token=token,
            body={
                "name": args.nas_name,
                "ip_address": ip,
                "shortname": "sim-nas",
                "nas_type": "other",
                "secret": NAS_SECRET,
                "description": "Simulated NAS container for testing RADIUS auth",
            },
        )
        device_id = result.get("id")
        if not device_id:
            print(f"  Failed: {result}", file=sys.stderr)
            sys.exit(1)
        print(f"  OK Created (id={device_id})")

    # 5. seed compose postgres (FreeRADIUS reads from it, not the alt)
    print("> Seeding FreeRADIUS database (compose postgres)...")
    try:
        subprocess.run(
            [
                "docker",
                "exec",
                "netgrid-postgres-1",
                "psql",
                "-U",
                "netgrid",
                "-d",
                "netgrid",
                "-c",
                """
             INSERT INTO subscribers (username, full_name, status, created_at, updated_at)
             VALUES ('demo-user', 'Demo Subscriber', 'active', NOW(), NOW())
             ON CONFLICT (username) DO NOTHING;

             INSERT INTO radcheck (username, attribute, op, value)
             VALUES ('demo-user', 'Cleartext-Password', ':=', 'demo-pass')
             ON CONFLICT DO NOTHING;
             """,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print("  OK demo-user seeded in compose postgres")
    except Exception as exc:
        print(f"  WARN Could not seed compose postgres: {exc}")

    # 5b. clear any lockout from earlier failed attempts
    print("> Clearing lockout counter...")
    try:
        subprocess.run(
            [
                "docker",
                "exec",
                "netgrid-postgres-1",
                "psql",
                "-U",
                "netgrid",
                "-d",
                "netgrid",
                "-c",
                "DELETE FROM radpostauth WHERE username = 'demo-user'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        print("  OK lockout cleared")
    except Exception:
        pass

    # 6. create test subscriber
    print("> Creating test subscriber demo-user / demo-pass...")
    try:
        # check if exists
        subs = _api("GET", "/api/v1/subscribers?page=1&page_size=100&q=demo-user", token=token)
        if any(s["username"] == "demo-user" for s in subs.get("items", [])):
            print("  OK Subscriber already exists")
        else:
            _api(
                "POST",
                "/api/v1/subscribers",
                token=token,
                body={
                    "username": "demo-user",
                    "full_name": "Demo Subscriber",
                    "password": "demo-pass",
                    "status": "active",
                },
            )
            print("  OK Created demo-user")
    except SystemExit:
        print("  WARN Could not create subscriber (API may not be running)")
        return

    # 7. test radtest
    print("> Testing RADIUS auth from FreeRADIUS container...")
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "netgrid-freeradius-1",
                "radtest",
                "demo-user",
                "demo-pass",
                "127.0.0.1",
                "1812",
                "testing123",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        if "Access-Accept" in output:
            print(f"  OK {output}")
        elif "Access-Reject" in output:
            print(f"  FAIL {output}")
        else:
            print(f"  WARN {output}")
    except Exception as exc:
        print(f"  WARN radtest failed: {exc}")

    # summary
    print()
    print("> Done. NAS device registered:")
    print(f"   Name:      {args.nas_name}")
    print(f"   IP:        {ip}")
    print(f"   Secret:    {NAS_SECRET}")
    print(f"   Device ID: {device_id}")
    print()
    print("> The sim-nas container is now sending RADIUS requests every 30s.")
    print("> Watch with: docker logs -f netgrid-sim-nas-1")


if __name__ == "__main__":
    main()
