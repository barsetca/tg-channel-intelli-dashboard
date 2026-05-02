"""Иерархия исключений для Telethon-сервиса: единый стиль ошибок под FastAPI и воркеры."""

from __future__ import annotations

from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.errors.rpcerrorlist import FloodTestPhoneWaitError


class TelegramTelethonError(Exception):
    """Базовая ошибка интеграции Telegram (перехват на уровне API/воркера)."""


class TelegramConfigurationError(TelegramTelethonError):
    """Нет API id/hash или некорректные пути сессии (сервис нельзя инициализировать)."""


class TelegramNotAuthorizedError(TelegramTelethonError):
    """Сессия на диске отсутствует или ключ не прошёл валидацию (ожидайте авторизацию)."""


class TelegramAuthRequiredError(TelegramTelethonError):
    """Клиент создан, но пользовательский вход ещё не завершён (нужна интерактивная первая авторизация)."""


class TelegramRateLimitedError(TelegramTelethonError):
    """
    Сервер Telegram попросил подождать (FloodWait / тестовый номер FloodTest).
    Атрибут ``retry_after_seconds`` — минимально рекомендуемая пауза в секундах.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TelegramUsernameNotFoundError(TelegramTelethonError):
    """@username или ссылка указывают на несуществующий публичный объект."""


class TelegramPrivateChannelError(TelegramTelethonError):
    """Канал существует, но недоступен текущей сессии (приват / бан и т.п.)."""


class TelegramInvalidIdentifierError(TelegramTelethonError):
    """Идентификатор передан некорректно или Telegram не смог резолвить сущность."""


def map_telethon_error(exc: BaseException) -> TelegramTelethonError | None:
    """
    Преобразует исключение Telethon в доменную ошибку.
    Если маппинга нет — возвращает ``None`` (вызывающий может пробросить оригинал).
    """
    if isinstance(exc, FloodWaitError):
        secs = getattr(exc, "seconds", None)
        msg = getattr(exc, "message", "") or repr(exc)
        return TelegramRateLimitedError(
            f"FloodWait: {msg}",
            retry_after_seconds=float(secs) if secs is not None else None,
        )
    if isinstance(exc, FloodTestPhoneWaitError):
        secs = getattr(exc, "seconds", None)
        return TelegramRateLimitedError(
            "Ограничение для тестового номера (FloodTestPhoneWait)",
            retry_after_seconds=float(secs) if secs is not None else None,
        )
    if isinstance(exc, (UsernameNotOccupiedError, UsernameInvalidError)):
        return TelegramUsernameNotFoundError(
            "Некорректное или свободное имя канала (@username)."
        )
    if isinstance(exc, ChannelPrivateError):
        return TelegramPrivateChannelError("Канал приватный или недоступен для этой сессии.")
    return None


def coerce_to_telegram_error(exc: BaseException, *, fallback_message: str) -> TelegramTelethonError:
    """Гарантированно возвращает ``TelegramTelethonError`` (оборачивает неизвестные)."""
    mapped = map_telethon_error(exc)
    if mapped is not None:
        return mapped
    if isinstance(exc, TelegramTelethonError):
        return exc
    wrapped = TelegramTelethonError(f"{fallback_message}: {exc}")
    wrapped.__cause__ = exc if exc else None  # сохранить цепочку для логов
    return wrapped
