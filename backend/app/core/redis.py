"""Async Redis client for short-lived caches and token revocation."""

from redis.asyncio import Redis

from .config import get_settings


def get_redis() -> Redis:
    """Return a fresh Redis client.

    Connection pools are bound to the event loop that created them, so a
    module-level singleton would leak across test loops (same failure mode as
    the Plan 1 asyncpg engine fix). Callers must ``await redis.aclose()``.
    """
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
