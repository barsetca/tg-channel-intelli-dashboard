import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401 — register ORM models with metadata for Alembic
from app.api.exception_handlers import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.integrations.telethon import TelethonUserSessionService
from app.integrations.telethon.interactive_auth import TelegramInteractiveAuthFlows
from app.orchestration.coordinator import OrchestrationCoordinator

log = logging.getLogger(__name__)


def configure_logging_from_settings() -> None:
    """
    Применяет `Settings.log_level` к корневому логгеру и ключевым логгерам uvicorn.

    Переменная окружения: **LOG_LEVEL** (см. `config.py`).
    Если не вызывать, uvicorn оставляет свои значения по умолчанию, а наш `LOG_LEVEL` в `.env`
    ни на что не влиял бы.
    """
    raw = (settings.log_level or "INFO").strip().upper()
    level = getattr(logging, raw, None)
    if not isinstance(level, int):
        level = logging.INFO
    # В docker/uvicorn root-handler может не быть настроен для app-логгеров.
    # Гарантируем вывод в stdout с единым форматом.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    root = logging.getLogger()
    root.setLevel(level)
    for prefix in ("app", "uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(prefix).setLevel(level)


configure_logging_from_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    coordinator = OrchestrationCoordinator(
        settings=settings,
        get_telegram=lambda: getattr(app.state, "telegram_service", None),
    )
    await coordinator.start()
    log.info(
        "app.lifespan OrchestrationCoordinator started (telegram_live queued jobs будут выполняться воркером)."
    )
    app.state.orchestration_coordinator = coordinator
    app.state.telegram_auth_flows = TelegramInteractiveAuthFlows()

    tg = TelethonUserSessionService(settings)
    telegram_ok, telegram_fail = await tg.startup_for_fastapi()
    if telegram_ok:
        app.state.telegram_service = tg
        app.state.telegram_startup_failure = None
        log.info("app.lifespan Telethon user session READY")
    else:
        try:
            await tg.disconnect()
        except Exception:  # noqa: BLE001
            pass
        app.state.telegram_service = None
        app.state.telegram_startup_failure = telegram_fail
        log.warning(
            "app.lifespan Telethon user session NOT available: %s",
            (telegram_fail or "unknown")[:280],
        )
    try:
        yield
    finally:
        svc = app.state.telegram_service
        if svc is not None:
            await svc.disconnect()
        flows = getattr(app.state, "telegram_auth_flows", None)
        if flows is not None:
            await flows.dispose_all()
        await coordinator.stop()
        await engine.dispose()


app = FastAPI(
    title="Telegram Channel Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

register_exception_handlers(app)
