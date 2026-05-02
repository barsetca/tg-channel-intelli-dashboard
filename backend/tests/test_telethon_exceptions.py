"""Юнит-тесты маппинга исключений Telethon → доменные ошибки."""

from __future__ import annotations

from telethon.errors import ChannelPrivateError, FloodWaitError, UsernameInvalidError

from app.integrations.telethon.exceptions import (
    TelegramPrivateChannelError,
    TelegramRateLimitedError,
    TelegramTelethonError,
    TelegramUsernameNotFoundError,
    coerce_to_telegram_error,
    map_telethon_error,
)


def test_map_flood_wait_sets_retry_seconds() -> None:
    # В Telethon: ``FloodWaitError(request, capture)`` → ``seconds=int(capture)``.
    mapped = map_telethon_error(FloodWaitError(None, 42))
    assert isinstance(mapped, TelegramRateLimitedError)
    assert mapped.retry_after_seconds == 42.0


def test_map_username_maps_to_not_found() -> None:
    mapped = map_telethon_error(UsernameInvalidError(None))
    assert isinstance(mapped, TelegramUsernameNotFoundError)


def test_map_channel_private() -> None:
    mapped = map_telethon_error(ChannelPrivateError("private"))
    assert isinstance(mapped, TelegramPrivateChannelError)


def test_coerce_wraps_unknown() -> None:
    err = coerce_to_telegram_error(RuntimeError("x"), fallback_message="внешняя ошибка")
    assert isinstance(err, TelegramTelethonError)
    assert "внешняя ошибка" in str(err)
    assert err.__cause__ is not None


def test_coerce_passes_already_mapped_rate_limit() -> None:
    orig = TelegramRateLimitedError("rl", retry_after_seconds=9.0)
    out = coerce_to_telegram_error(orig, fallback_message="не должно встречаться")
    assert out is orig

