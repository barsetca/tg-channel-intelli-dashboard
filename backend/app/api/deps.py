from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.services.channel_service import ChannelService
from app.services.health_service import HealthService


def get_settings_dep() -> Settings:
    return get_settings()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


def get_health_service(
    settings: Settings = Depends(get_settings_dep),
) -> HealthService:
    return HealthService(settings)


def get_channel_service(
    session: AsyncSession = Depends(get_session),
) -> ChannelService:
    return ChannelService(session)
