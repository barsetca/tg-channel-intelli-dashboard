"""Состояние интеграции Telegram для UI (поиск live, модалка входа)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TelegramIntegrationStatus(BaseModel):
    """Публичный снимок: можно ли искать в live и доступен ли HTTP-вход."""

    api_configured: bool = Field(..., description="Заданы TELEGRAM_API_ID и TELEGRAM_API_HASH")
    session_ready: bool = Field(..., description="Поднят TelethonUserSessionService при старте API")
    interactive_login_enabled: bool = Field(
        ...,
        description="Флаг TELEGRAM_INTERACTIVE_LOGIN (разрешён ли пошаговый вход)",
    )
    interactive_login_available: bool = Field(
        ...,
        description="Можно вызвать POST /telegram/auth/* (ключи есть и вход не выключен)",
    )
    startup_failure: str | None = Field(
        None,
        description="Краткая причина, если session_ready=false при наличии api_id/hash",
    )
