from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.integrations.telethon.user_session_service import TelethonUserSessionService
from app.services.channel_service import ChannelService
from app.services.health_service import HealthService
from app.services.intelligence_service import IntelligenceService
from app.services.vector_service import VectorService


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


def get_intelligence_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> IntelligenceService:
    """Сервис сценариев intelligence (поиск, анализ, сравнение, экспорт)."""
    coordinator = getattr(request.app.state, "orchestration_coordinator", None)
    telegram = getattr(request.app.state, "telegram_service", None)
    telethon_ok = getattr(request.app.state, "telegram_service", None) is not None
    telethon_startup_failure = getattr(request.app.state, "telegram_startup_failure", None)
    return IntelligenceService(
        session,
        coordinator=coordinator,
        telegram=telegram,
        telethon_live_available=telethon_ok,
        telethon_startup_failure=telethon_startup_failure,
    )


async def get_vector_service() -> AsyncGenerator[VectorService, None]:
    """
    Жизненный цикл VectorService на запрос: connect при входе, close при выходе.

    Так Qdrant/OpenAI клиенты не висят глобально между запросами.
    """
    svc = VectorService()
    await svc.connect()
    try:
        yield svc
    finally:
        await svc.close()


def get_telethon_user_session_service_dep(request: Request) -> TelethonUserSessionService:
    """
    Возвращает подключённый Telethon-сервис из ``app.state``
    (lifespan создаёт сессию при старте).

    Если клиент недоступен (нет ключей или сессии), отвечает 503;
    эндпоинты трактуют это как временную деградацию.
    """
    svc = getattr(request.app.state, "telegram_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Интеграция Telegram (пользовательская сессия) недоступна: "
                "проверьте TELEGRAM_API_ID/HASH, TELEGRAM_SESSION (StringSession) или авторизованный .session файл."
            ),
        )
    return cast(TelethonUserSessionService, svc)


TelethonUserSessionServiceDep = Annotated[
    TelethonUserSessionService,
    Depends(get_telethon_user_session_service_dep),
]
