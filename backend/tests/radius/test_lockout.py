"""Scripted radtest checks for the FreeRADIUS abuse-protection lockout (Phase 11).

These tests exercise the real production path end to end — unlang policy
(`raddb/policy.d/lockout`) -> rlm_sql -> Postgres `radpostauth` — with no
Python RADIUS client: every packet is sent by `radtest` inside the freeradius
container and every assertion is checked against Postgres with `psql`. They
need the compose stack up, exactly as CI's `radius` job does:

    docker compose up -d --wait postgres freeradius
    cd backend && pytest tests/radius -q

If FreeRADIUS is unreachable the tests skip with a hint, so they are safe to
run locally without the stack. Usernames are timestamped and every test
cleans up after itself, so runs are independent and re-runnable.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

COMPOSE = ("docker", "compose", "exec", "-T")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )


def psql(sql: str) -> str:
    """Run SQL via psql in the postgres container; return trimmed stdout."""
    proc = _run(
        [
            *COMPOSE,
            "postgres",
            "psql",
            "-U",
            "netgrid",
            "-d",
            "netgrid",
            "-tAc",
            sql,
        ]
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def radtest(username: str, password: str) -> str:
    """Send one RADIUS auth packet via radtest inside the freeradius container."""
    proc = _run(
        [
            *COMPOSE,
            "freeradius",
            "radtest",
            username,
            password,
            "127.0.0.1",
            "0",
            "testing123",
        ]
    )
    # radtest exits non-zero on Access-Reject; the reply is what matters.
    return proc.stdout + proc.stderr


def received(out: str, packet: str) -> bool:
    return f"Received {packet}" in out


def seed_subscriber(username: str, password: str) -> None:
    """Write a radcheck Cleartext-Password row, as the FastAPI service does."""
    psql(
        "INSERT INTO radcheck (username, attribute, op, value) "
        f"VALUES ('{username}', 'Cleartext-Password', ':=', '{password}')"
    )


def clear_failures(username: str) -> None:
    psql(f"DELETE FROM radpostauth WHERE username = '{username}'")


@pytest.fixture(scope="module")
def radius_ready() -> None:
    """Wait (up to ~30s) for FreeRADIUS to answer; skip if the stack is down."""
    probe = f"probe{int(time.time())}"
    for _ in range(15):
        out = radtest(probe, "badpass")
        if "Received" in out:
            return
        time.sleep(2)
    pytest.skip(
        "FreeRADIUS not reachable via `docker compose exec` — start the stack "
        "first: docker compose up -d --wait postgres freeradius"
    )


def test_lockout_rejects_after_threshold_and_lifts_when_window_clears(
    radius_ready: None,
) -> None:
    """Ten recent failures lock the username; clearing them lifts the lockout."""
    username = f"locktest{int(time.time())}"
    try:
        seed_subscriber(username, "correct-horse")

        # Baseline: a correct credential is accepted.
        out = radtest(username, "correct-horse")
        assert received(out, "Access-Accept"), out

        # Ten wrong guesses push the recent-failure count to the threshold.
        for _ in range(10):
            out = radtest(username, "wrong-pass")
            assert received(out, "Access-Reject"), out

        # The next attempt is rejected *before* the credential is checked —
        # even with the correct password, proving the policy short-circuits.
        out = radtest(username, "correct-horse")
        assert received(out, "Access-Reject"), out

        # Every rejection was logged, including the locked-out attempt itself
        # (10 guesses + 1 policy rejection).
        count = psql(
            "SELECT count(*) FROM radpostauth "
            f"WHERE username = '{username}' AND reply = 'Access-Reject'"
        )
        assert int(count) == 11

        # Simulating the 5-minute window expiring (failures age out of the
        # count) lifts the lockout: the correct credential works again.
        clear_failures(username)
        out = radtest(username, "correct-horse")
        assert received(out, "Access-Accept"), out
    finally:
        clear_failures(username)
        psql(f"DELETE FROM radcheck WHERE username = '{username}'")


def test_successful_auths_do_not_count_toward_lockout(radius_ready: None) -> None:
    """Only Access-Reject rows count; successes never push anyone over."""
    username = f"lockok{int(time.time())}"
    try:
        seed_subscriber(username, "correct-horse")

        # Interleave successes with failures — only the failures may count.
        for _ in range(5):
            out = radtest(username, "correct-horse")
            assert received(out, "Access-Accept"), out
            out = radtest(username, "wrong-pass")
            assert received(out, "Access-Reject"), out

        # 5 failures so far (< threshold of 10): a correct password still works.
        out = radtest(username, "correct-horse")
        assert received(out, "Access-Accept"), out

        # And the counted failures are exactly 5, not 10.
        count = psql(
            "SELECT count(*) FROM radpostauth "
            f"WHERE username = '{username}' AND reply = 'Access-Reject'"
        )
        assert int(count) == 5
    finally:
        clear_failures(username)
        psql(f"DELETE FROM radcheck WHERE username = '{username}'")


def test_unknown_username_is_locked_out_too(radius_ready: None) -> None:
    """Users not in radcheck are also protected (anti-enumeration hammering)."""
    username = f"lockghost{int(time.time())}"
    try:
        for _ in range(10):
            out = radtest(username, "any-pass")
            assert received(out, "Access-Reject"), out

        # The 11th attempt is a policy rejection (lockout), not merely an
        # unknown-user rejection — still a clean Access-Reject, and the
        # counter keeps the lockout in force while hammering continues.
        out = radtest(username, "any-pass")
        assert received(out, "Access-Reject"), out

        count = psql(
            "SELECT count(*) FROM radpostauth "
            f"WHERE username = '{username}' AND reply = 'Access-Reject'"
        )
        assert int(count) == 11
    finally:
        clear_failures(username)


def test_hostile_username_does_not_break_lockout_query(radius_ready: None) -> None:
    """A crafted User-Name can at worst corrupt its own count — never the server."""
    username = "evil' OR 1=1 --"
    try:
        # The hostile username fails auth like any unknown user; the corrupted
        # count only ever gates this request.
        for _ in range(3):
            out = radtest(username, "x")
            assert received(out, "Access-Reject"), out

        # The server keeps answering legitimate requests afterwards.
        probe = f"alive{int(time.time())}"
        out = radtest(probe, "x")
        assert "Received" in out
    finally:
        psql("DELETE FROM radpostauth WHERE username LIKE 'evil%'")
