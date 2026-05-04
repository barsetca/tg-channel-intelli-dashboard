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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    coordinator = OrchestrationCoordinator()
    await coordinator.start()
    app.state.orchestration_coordinator = coordinator
    app.state.telegram_auth_flows = TelegramInteractiveAuthFlows()

    tg = TelethonUserSessionService(settings)
    telegram_ok, telegram_fail = await tg.startup_for_fastapi()
    if telegram_ok:
        app.state.telegram_service = tg
        app.state.telegram_startup_failure = None
    else:
        try:
            await tg.disconnect()
        except Exception:  # noqa: BLE001
            pass
        app.state.telegram_service = None
        app.state.telegram_startup_failure = telegram_fail
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
