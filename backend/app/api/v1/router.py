from fastapi import APIRouter

from .admins import router as admins_router
from .auth import router as auth_router
from .health import router as health_router
from .roles import permissions_router
from .roles import router as roles_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(admins_router)
api_router.include_router(roles_router)
api_router.include_router(permissions_router)
