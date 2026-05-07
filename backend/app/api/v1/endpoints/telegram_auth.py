"""Интерактивный первый вход Telethon: телефон → код → при необходимости пароль 2FA."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_settings_dep
from app.core.config import Settings
from app.integrations.telethon.exceptions import (
    TelegramConfigurationError,
    TelegramInvalidIdentifierError,
    TelegramTelethonError,
)
from app.integrations.telethon.interactive_auth import TelegramInteractiveAuthFlows
from app.schemas.telegram_auth import TelegramAuthCodeBody, TelegramAuthPasswordBody, TelegramAuthStartBody
from app.schemas.telegram_status import TelegramIntegrationStatus

router = APIRouter()


@router.get(
    "/status",
    response_model=TelegramIntegrationStatus,
    summary="Состояние сессии Telegram для UI",
    description="Перед поиском «Telegram live» фронт проверяет session_ready и при необходимости открывает вход.",
)
async def telegram_integration_status(request: Request, settings: Settings = Depends(get_settings_dep)) -> TelegramIntegrationStatus:
    api_configured = bool(settings.telegram_api_id and settings.telegram_api_hash)
    session_ready = getattr(request.app.state, "telegram_service", None) is not None
    interactive_on = bool(settings.telegram_interactive_login_enabled)
    interactive_login_available = interactive_on and api_configured
    startup_failure = getattr(request.app.state, "telegram_startup_failure", None)
    if session_ready:
        startup_failure = None
    return TelegramIntegrationStatus(
        api_configured=api_configured,
        session_ready=session_ready,
        interactive_login_enabled=interactive_on,
        interactive_login_available=interactive_login_available,
        startup_failure=startup_failure if isinstance(startup_failure, str) else None,
    )


def _auth_flows(request: Request) -> TelegramInteractiveAuthFlows:
    flows = getattr(request.app.state, "telegram_auth_flows", None)
    if flows is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Потоки интерактивного входа не инициализированы.",
        )
    return flows


def _to_http(exc: BaseException) -> HTTPException:
    if isinstance(exc, TelegramConfigurationError):
        return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    if isinstance(exc, TelegramInvalidIdentifierError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, TelegramTelethonError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/auth/start",
    summary="Запросить код входа Telegram",
    description="Отправляет SMS/Telegram-код на указанный номер. Возвращает flow_id для шага с кодом.",
)
async def telegram_auth_start(
    request: Request,
    body: TelegramAuthStartBody,
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, object]:
    if not settings.telegram_interactive_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Интерактивный вход отключён (TELEGRAM_INTERACTIVE_LOGIN=false).",
        )
    flows = _auth_flows(request)
    try:
        flow_id = await flows.start(settings, phone=body.phone)
    except (TelegramTelethonError, TelegramInvalidIdentifierError, TelegramConfigurationError) as exc:
        raise _to_http(exc) from exc
    return {"flow_id": flow_id, "expires_in_seconds": 600}


@router.post(
    "/auth/code",
    summary="Подтвердить код",
    description="После успеха возвращает telegram_session (StringSession) и поднимает основной клиент в приложении.",
)
async def telegram_auth_code(
    request: Request,
    body: TelegramAuthCodeBody,
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, object]:
    if not settings.telegram_interactive_login_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Интерактивный вход отключён.")
    flows = _auth_flows(request)
    try:
        return await flows.submit_code(settings, flow_id=body.flow_id, code=body.code, app=request.app)
    except (TelegramTelethonError, TelegramInvalidIdentifierError, TelegramConfigurationError) as exc:
        raise _to_http(exc) from exc


@router.post(
    "/auth/password",
    summary="Пароль 2FA",
    description="Вызывается, если шаг с кодом вернул status=needs_password.",
)
async def telegram_auth_password(
    request: Request,
    body: TelegramAuthPasswordBody,
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, object]:
    if not settings.telegram_interactive_login_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Интерактивный вход отключён.")
    flows = _auth_flows(request)
    try:
        return await flows.submit_password(settings, flow_id=body.flow_id, password=body.password, app=request.app)
    except (TelegramTelethonError, TelegramInvalidIdentifierError, TelegramConfigurationError) as exc:
        raise _to_http(exc) from exc
