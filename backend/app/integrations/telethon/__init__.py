"""
Telegram (MTProto, user session) через Telethon — асинхронный клиентский слой.

Подключение: пользовательская сессия (*.session файл), см. документацию в
``backend/docs/TELEGRAM_TELETHON.md``.
"""

from app.integrations.telethon.dto import (
    TelegramChannelFullInfo,
    TelegramPostBrief,
    TelegramSearchHit,
)
from app.integrations.telethon.exceptions import (
    TelegramAuthRequiredError,
    TelegramConfigurationError,
    TelegramInvalidIdentifierError,
    TelegramNotAuthorizedError,
    TelegramPrivateChannelError,
    TelegramRateLimitedError,
    TelegramTelethonError,
    TelegramUsernameNotFoundError,
    coerce_to_telegram_error,
    map_telethon_error,
)
from app.integrations.telethon.user_session_service import TelethonUserSessionService

__all__ = [
    "TelethonUserSessionService",
    "TelegramChannelFullInfo",
    "TelegramPostBrief",
    "TelegramSearchHit",
    "TelegramTelethonError",
    "TelegramConfigurationError",
    "TelegramAuthRequiredError",
    "TelegramNotAuthorizedError",
    "TelegramRateLimitedError",
    "TelegramUsernameNotFoundError",
    "TelegramPrivateChannelError",
    "TelegramInvalidIdentifierError",
    "coerce_to_telegram_error",
    "map_telethon_error",
]
