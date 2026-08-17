from fastapi import FastAPI

from .api.v1.router import api_router
from .core.errors import register_exception_handlers
from .core.rate_limit import limiter, register_rate_limit_handler


def create_app() -> FastAPI:
    app = FastAPI(title="NetGrid API", version="0.1.0")
    app.include_router(api_router, prefix="/api/v1")
    register_exception_handlers(app)
    app.state.limiter = limiter
    register_rate_limit_handler(app)
    return app


app = create_app()
