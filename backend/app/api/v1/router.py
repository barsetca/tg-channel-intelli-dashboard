from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyze,
    channel_one,
    channels,
    compare,
    export_data,
    health,
    orchestration_jobs,
    recommendations,
    search_channels,
    semantic_search,
    telegram_auth,
)

api_router = APIRouter()

# Системные
api_router.include_router(health.router, tags=["health"])

# Каталог каналов (CRUD MVP)
api_router.include_router(channels.router, prefix="/channels", tags=["channels"])

# Сценарии из context/user_scenario.txt
api_router.include_router(search_channels.router, prefix="/search-channels", tags=["search"])
api_router.include_router(channel_one.router, prefix="/channel", tags=["channel"])
api_router.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
api_router.include_router(semantic_search.router, prefix="/semantic-search", tags=["semantic"])
api_router.include_router(
    recommendations.router,
    prefix="/recommendations",
    tags=["recommendations"],
)
api_router.include_router(compare.router, prefix="/channels", tags=["compare"])
api_router.include_router(export_data.router, prefix="/export", tags=["export"])
api_router.include_router(telegram_auth.router, prefix="/telegram", tags=["telegram-auth"])
api_router.include_router(orchestration_jobs.router, prefix="/orchestration", tags=["orchestration"])
