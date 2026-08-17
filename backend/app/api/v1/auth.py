"""Auth endpoints: login, refresh, logout, me.

These four endpoints are the pre-RBAC exception to the "explicit permission
on every endpoint" rule — they are the authentication layer itself. Plan 3
(RBAC) adds permission checks to /auth/me and everywhere else.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.db import get_session
from app.core.rate_limit import LIMITS, limiter
from app.models.rbac import Admin
from app.schemas.auth import (
    AdminOut,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/login", response_model=LoginResponse)
@limiter.limit(LIMITS["login"])
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: SessionDep,
) -> LoginResponse:
    """POST /api/v1/auth/login — no permission required (auth endpoint)."""
    admin = await auth_service.authenticate_admin(session, payload.username, payload.password)
    pair = await auth_service.build_token_pair(session, admin)
    return LoginResponse(admin=AdminOut.model_validate(admin), **pair)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(LIMITS["refresh"])
async def refresh(
    request: Request, response: Response, payload: RefreshRequest, session: SessionDep
) -> TokenPair:
    """POST /api/v1/auth/refresh — no permission required (auth endpoint)."""
    return TokenPair(**await auth_service.refresh_tokens(session, payload.refresh_token))


@router.post("/logout", status_code=204)
@limiter.limit(LIMITS["logout"])
async def logout(request: Request, response: Response, payload: LogoutRequest) -> Response:
    """POST /api/v1/auth/logout — no permission required (auth endpoint)."""
    await auth_service.logout(payload.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=AdminOut)
@limiter.limit(LIMITS["me"])
async def me(
    request: Request,
    response: Response,
    admin: Annotated[Admin, Depends(get_current_admin)],
) -> AdminOut:
    """GET /api/v1/auth/me — requires a valid access token (auth-only until Plan 3)."""
    return AdminOut.model_validate(admin)
