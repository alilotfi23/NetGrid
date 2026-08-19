from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from .api.v1.router import api_router
from .core.errors import register_exception_handlers
from .core.rate_limit import limiter, register_rate_limit_handler
from .jobs.invoice_generation import build_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start background jobs with the app; shut them down cleanly on exit."""
    scheduler: AsyncIOScheduler | None = None
    if not app.state.testing:
        scheduler = build_scheduler()
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="NetGrid API", version="0.1.0", lifespan=lifespan)
    app.state.testing = False
    app.include_router(api_router, prefix="/api/v1")
    register_exception_handlers(app)
    app.state.limiter = limiter
    register_rate_limit_handler(app)
    return app


app = create_app()
