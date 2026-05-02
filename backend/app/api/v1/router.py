from fastapi import APIRouter

from app.api.v1.endpoints import channels, health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(channels.router, prefix="/channels", tags=["channels"])
