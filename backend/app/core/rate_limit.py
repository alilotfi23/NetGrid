"""Centralized API rate limiting (slowapi + Redis).

Auth endpoints get strict limits (see CLAUDE.md Rate Limiting). Phase 8
expands this module to tiered limits across all routes — limits stay here,
never scattered as magic numbers per router.
"""

import os
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from .config import get_settings

# Two namespaces keep test resets isolated: slowapi's `key_prefix` nests
# inside the item name, but limiter.reset() clears keys by the *storage*
# prefix (the limits library's own, default "LIMITS" otherwise) — so the
# storage prefix is what actually scopes resets. Under pytest-xdist every
# worker process imports this module fresh, and each worker gets its own
# storage prefix: the shared counters (and per-test resets) would otherwise
# race across parallel workers and spuriously 429 unrelated tests.
_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().redis_url,
    headers_enabled=True,
    key_prefix="netgrid-rl",
    storage_options={
        "key_prefix": f"netgrid-rl-{_worker}" if _worker else "netgrid-rl"
    },
)

LIMITS = {
    "login": "5/minute",
    "refresh": "10/minute",
    "logout": "10/minute",
    "me": "60/minute",
    # Phase 3 management endpoints: reads loose, writes moderate.
    "admin_read": "60/minute",
    "admin_write": "20/minute",
    # Phase 5 subscriber endpoints: reads loose, writes moderate.
    "subscriber_read": "60/minute",
    "subscriber_write": "20/minute",
    # Phase 6 plan endpoints: same tiers.
    "plan_read": "60/minute",
    "plan_write": "20/minute",
    # Phase 10 invoice endpoints: reads loose, writes moderate (a payment
    # record is a write-ish financial action).
    "invoice_read": "60/minute",
    "invoice_write": "20/minute",
    # Phase 7 NAS device endpoints: same tiers.
    "nas_read": "60/minute",
    "nas_write": "20/minute",
    # Phase 9 live-session endpoints: reads loose, disconnects moderate
    # (a disconnect is a write-ish action against a live NAS).
    "sessions_read": "60/minute",
    "sessions_disconnect": "10/minute",
    # Phase 12 audit log viewer: read-only.
    "audit_read": "60/minute",
    # Data-cap usage report: read-only.
    "usage_read": "60/minute",
}


def register_rate_limit_handler(app: FastAPI) -> None:
    """429 handler matching the project error envelope + Retry-After header."""

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
        response: Response = JSONResponse(
            status_code=429,
            content={
                "error": {"code": "RATE_LIMITED", "message": "Rate limit exceeded, try again later"}
            },
        )
        view_limit = getattr(request.state, "view_rate_limit", None)
        if view_limit is not None:
            # request.app is typed ASGIApp; cast to FastAPI for mypy --strict.
            response = cast(FastAPI, request.app).state.limiter._inject_headers(
                response, view_limit
            )
        return response
