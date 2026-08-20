"""Effective-permission resolution for admins, with a short-TTL Redis cache.

The cache is best-effort: a Redis outage falls back to DB resolution and
skips caching, so RBAC never breaks auth.
"""

import json
import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import PERM_CACHE_TTL_SECONDS, version_of
from app.core.redis import get_redis
from app.models.rbac import Admin, Permission, Role, admin_roles, role_permissions

# Under pytest-xdist each worker runs its own database where admin ids start
# at 1 again — a shared cache keyed only by admin id would serve one worker's
# permission set to another's. Namespace by worker when running in parallel.
_worker = os.environ.get("PYTEST_XDIST_WORKER", "")
CACHE_KEY = f"rbac:perms:{_worker}:{{}}" if _worker else "rbac:perms:{}"


@dataclass(frozen=True)
class PermissionState:
    version: str
    codes: frozenset[str]


async def resolve_admin_permissions(session: AsyncSession, admin_id: int) -> set[str]:
    """Union of permission codes across the admin's roles.

    Written as an explicit join rather than an eager-loaded relationship: the
    admin may already be in the session's identity map (loaded without roles),
    in which case eager-load options are ignored and ``admin.roles`` would
    trigger a lazy load (MissingGreenlet under asyncpg).
    """
    result = await session.execute(
        select(Permission.code)
        .select_from(Admin)
        .join(admin_roles, admin_roles.c.admin_id == Admin.id)
        .join(Role, Role.id == admin_roles.c.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(Admin.id == admin_id)
    )
    return set(result.scalars().all())


async def _read_cache(admin_id: int) -> PermissionState | None:
    redis = get_redis()
    try:
        raw = await redis.get(CACHE_KEY.format(admin_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return PermissionState(data["version"], frozenset(data["codes"]))
    except Exception:
        return None  # cache outage -> slow path
    finally:
        await redis.aclose()


async def _write_cache(admin_id: int, state: PermissionState) -> None:
    redis = get_redis()
    try:
        await redis.set(
            CACHE_KEY.format(admin_id),
            json.dumps({"version": state.version, "codes": sorted(state.codes)}),
            ex=PERM_CACHE_TTL_SECONDS,
        )
    except Exception:
        pass  # best-effort
    finally:
        await redis.aclose()


async def get_permission_state(session: AsyncSession, admin_id: int) -> PermissionState:
    cached = await _read_cache(admin_id)
    if cached is not None:
        return cached
    codes = await resolve_admin_permissions(session, admin_id)
    state = PermissionState(version_of(codes), frozenset(codes))
    await _write_cache(admin_id, state)
    return state


async def invalidate_admin_permissions(admin_id: int) -> None:
    """Drop the cached permission set (call after any role/permission change)."""
    redis = get_redis()
    try:
        await redis.delete(CACHE_KEY.format(admin_id))
    except Exception:
        pass  # TTL self-heals
    finally:
        await redis.aclose()
