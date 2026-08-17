import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  # register every model on Base.metadata
from app.core.config import get_settings
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
