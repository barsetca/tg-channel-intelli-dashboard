from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401 — register ORM models with metadata for Alembic
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.integrations.telethon import TelethonUserSessionService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    tg = TelethonUserSessionService(settings)
    telegram_ok = await tg.startup_for_fastapi()
    app.state.telegram_service = tg if telegram_ok else None
    try:
        yield
    finally:
        svc = app.state.telegram_service
        if svc is not None:
            await svc.disconnect()
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
