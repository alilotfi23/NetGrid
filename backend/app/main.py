from fastapi import FastAPI

from .api.v1.router import api_router
from .core.errors import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="NetGrid API", version="0.1.0")
    app.include_router(api_router, prefix="/api/v1")
    register_exception_handlers(app)
    return app


app = create_app()
