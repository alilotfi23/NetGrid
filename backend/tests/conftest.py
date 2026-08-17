import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  # register every model on Base.metadata
from app.core.config import get_settings
from app.core.db import get_session
from app.core.rate_limit import limiter as app_limiter
from app.main import create_app
from app.models.base import Base


@pytest_asyncio.fixture
async def engine():
    # Function-scoped so each test's event loop owns its connection pool; a
    # session-scoped engine would hand pooled connections across loops and
    # asyncpg raises "another operation is in progress".
    engine = create_async_engine(get_settings().test_database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
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
    app_limiter.reset()
    test_app.dependency_overrides[get_session] = lambda: session
    yield test_app
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
