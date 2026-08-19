"""Centralized API rate limiting (slowapi + Redis).

Auth endpoints get strict limits (see CLAUDE.md Rate Limiting). Phase 8
expands this module to tiered limits across all routes — limits stay here,
never scattered as magic numbers per router.
"""

from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from .config import get_settings

# key_prefix namespaces limiter keys so tests can limiter.reset() the whole
# namespace without touching any other Redis data.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().redis_url,
    headers_enabled=True,
    key_prefix="netgrid-rl",
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
