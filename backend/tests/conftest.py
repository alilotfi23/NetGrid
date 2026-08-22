import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  # register every model on Base.metadata
from app.core.config import get_settings
from app.core.db import get_session
from app.core.rate_limit import limiter as app_limiter
from app.core.redis import get_redis
from app.main import create_app
from app.models.base import Base


def _test_database_url() -> str:
    """The test DB URL, per pytest-xdist worker when running in parallel.

    pytest-xdist sets ``PYTEST_XDIST_WORKER`` (e.g. ``gw0``) in each worker
    process. Serial runs — no xdist, or the master controller where the env
    var is unset — use the configured ``netgrid_test`` database as before.
    Parallel workers each get their own database (``netgrid_test_gw0``,
    ``netgrid_test_gw1``, ...) because the function-scoped session fixture
    drops and recreates every table per test: a shared database would let
    one worker's drop_all clobber another worker's in-flight test.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    base = get_settings().test_database_url
    if not worker or worker == "master":
        return base
    return base.rsplit("/", 1)[0] + f"/netgrid_test_{worker}"


async def _ensure_database(name: str) -> None:
    """Create the worker database if missing (netgrid owns the postgres server).

    CREATE DATABASE cannot run inside a transaction, so the maintenance
    connection uses AUTOCOMMIT; it connects to the always-present ``netgrid``
    database (not the target) so a missing target never breaks the connect.
    """
    settings = get_settings()
    maintenance = settings.test_database_url.rsplit("/", 1)[0] + "/netgrid"
    admin_engine = create_async_engine(maintenance, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await admin_engine.dispose()


async def _clear_rbac_cache() -> None:
    """Drop stale rbac:perms:* keys.

    Postgres sequences are not reset by drop_all/create_all, so admin ids are
    reused across pytest runs — a stale permission cache from a previous run
    (TTL 60s) would otherwise serve an old permission set to a fresh test.
    """
    redis = get_redis()
    try:
        async for key in redis.scan_iter("rbac:perms:*"):
            await redis.delete(key)
    except Exception:
        pass
    finally:
        await redis.aclose()


async def _clear_usage_cache() -> None:
    """Drop stale usage:* keys.

    The usage service caches per-subscriber aggregates in Redis (TTL 60s);
    tests seed the same demo usernames against a fresh database, so a leftover
    cache entry from an earlier test in the same run would serve an old value.
    """
    redis = get_redis()
    try:
        async for key in redis.scan_iter("usage:*"):
            await redis.delete(key)
    except Exception:
        pass
    finally:
        await redis.aclose()


@pytest_asyncio.fixture
async def engine():
    # Function-scoped so each test's event loop owns its connection pool; a
    # session-scoped engine would hand pooled connections across loops and
    # asyncpg raises "another operation is in progress".
    url = _test_database_url()
    if url != get_settings().test_database_url:
        await _ensure_database(url.rsplit("/", 1)[1])
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await _clear_rbac_cache()
    await _clear_usage_cache()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def app(session):
    """Fresh FastAPI app per test, wired to the test DB session.

    Rate-limit counters persist in Redis between tests, so the netgrid-rl
    namespace is reset first; blacklist keys are unique per token and expire,
    so they need no cleanup.
    """
    test_app = create_app()
    test_app.state.testing = True  # lifespan must not start the APScheduler in tests
    app_limiter.reset()
    test_app.dependency_overrides[get_session] = lambda: session
    yield test_app
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
