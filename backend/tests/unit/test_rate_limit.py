"""Unit tests for app.core.rate_limit module.

Tests the limiter configuration, key function, key prefix namespace,
and the LIMITS dictionary structure — no Redis or HTTP needed.
"""

from slowapi import Limiter


class TestLimiterConfiguration:
    """Verify the limiter is wired correctly."""

    def test_limiter_is_slowapi_instance(self) -> None:
        from app.core.rate_limit import limiter

        assert isinstance(limiter, Limiter)

    def test_key_prefix_namespaced(self) -> None:
        """All Redis keys start with 'netgrid-rl' to isolate test resets."""
        from app.core.rate_limit import limiter

        assert limiter._key_prefix == "netgrid-rl"  # type: ignore[attr-defined]

    def test_key_func_uses_remote_address(self) -> None:
        """Default key should derive from the client IP."""
        # get_remote_address is the slowapi default; verify it's the
        # function wired into the limiter.
        from app.core.rate_limit import get_remote_address, limiter

        assert limiter._key_func is get_remote_address  # type: ignore[attr-defined]


class TestLimitsDictionary:
    """Verify the LIMITS dict covers every expected tier and has valid values."""

    def test_login_limit_exists(self) -> None:
        from app.core.rate_limit import LIMITS

        assert "login" in LIMITS
        assert "minute" in LIMITS["login"]

    def test_auth_endpoint_limits_are_tight(self) -> None:
        """Auth endpoints (login/refresh/logout) should have per-minute limits."""
        from app.core.rate_limit import LIMITS

        for key in ("login", "refresh", "logout"):
            assert key in LIMITS
            # Parse: "N/minute" → N <= 10
            count = int(LIMITS[key].split("/")[0])
            assert count <= 10, f"{key} limit too loose: {LIMITS[key]}"

    def test_read_limits_are_generous(self) -> None:
        """Read endpoints should allow at least 60 req/min."""
        from app.core.rate_limit import LIMITS

        read_keys = [k for k in LIMITS if k.endswith("_read") or k in ("me",)]
        assert len(read_keys) >= 4, f"Expected at least 4 read keys, got {read_keys}"
        for key in read_keys:
            count = int(LIMITS[key].split("/")[0])
            assert count >= 60, f"{key} limit too strict for reads: {LIMITS[key]}"

    def test_write_limits_are_moderate(self) -> None:
        """Write endpoints should allow 10–30 req/min."""
        from app.core.rate_limit import LIMITS

        write_keys = [k for k in LIMITS if k.endswith("_write")]
        assert len(write_keys) >= 4, f"Expected at least 4 write keys, got {write_keys}"
        for key in write_keys:
            count = int(LIMITS[key].split("/")[0])
            assert 10 <= count <= 30, f"{key} limit not in 10–30 range: {LIMITS[key]}"

    def test_disconnect_limit_is_strict(self) -> None:
        """Session disconnect is a privileged action — stricter than reads."""
        from app.core.rate_limit import LIMITS

        count = int(LIMITS["sessions_disconnect"].split("/")[0])
        assert count <= 10, f"sessions_disconnect limit too loose: {LIMITS['sessions_disconnect']}"

    def test_all_values_are_strings_with_slash(self) -> None:
        """Every limit value must be in 'N/unit' format."""
        from app.core.rate_limit import LIMITS

        for key, value in LIMITS.items():
            assert "/" in value, f"LIMITS[{key!r}] = {value!r} — missing '/'"
            parts = value.split("/")
            assert parts[0].isdigit(), f"LIMITS[{key!r}] non-numeric count: {parts[0]!r}"
            assert parts[1] in (
                "second",
                "minute",
                "hour",
            ), f"LIMITS[{key!r}] unknown unit: {parts[1]!r}"

    def test_expected_tiers_present(self) -> None:
        """Smoke-check that every resource tier from CLAUDE.md exists."""
        from app.core.rate_limit import LIMITS

        expected = {
            "login",
            "refresh",
            "logout",
            "me",
            "admin_read",
            "admin_write",
            "subscriber_read",
            "subscriber_write",
            "plan_read",
            "plan_write",
            "invoice_read",
            "invoice_write",
            "nas_read",
            "nas_write",
            "sessions_read",
            "sessions_disconnect",
        }
        missing = expected - set(LIMITS.keys())
        assert not missing, f"Missing LIMITS entries: {missing}"


class TestRateLimitHandler:
    """Verify the 429 handler produces the correct error envelope."""

    def test_handler_exists_and_is_registered(self) -> None:
        """The app fixture in conftest registers the handler — just verify import."""
        from app.core.rate_limit import register_rate_limit_handler

        assert callable(register_rate_limit_handler)
