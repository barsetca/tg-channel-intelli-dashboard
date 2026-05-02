"""Обёртки повторов при FloodWait: уважаем указанную Telegram паузу с ограничением сверху (кап для UX)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.integrations.telethon.exceptions import (
    TelegramRateLimitedError,
    TelegramTelethonError,
    map_telethon_error,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def run_with_optional_flood_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    max_additional_attempts: int,
    cap_sleep_seconds: int,
    operation_label: str = "telethon_op",
) -> T:
    """
    Выполняет асинхронную операцию, при FloodWait делает паузу и повторяет.

    * ``max_additional_attempts`` — сколько дополнительных попыток после первой ошибки (итого попыток 1 + N).
    * ``cap_sleep_seconds`` — максимум ожидания за один FloodWait (иногда Telegram просят часы).
    """
    attempt = 0
    limit = max_additional_attempts + 1
    last_error: BaseException | None = None

    while attempt < limit:
        try:
            return await factory()
        except Exception as exc:
            mapped = map_telethon_error(exc)
            if not isinstance(mapped, TelegramRateLimitedError):
                raise
            last_error = mapped
            wait_sec = mapped.retry_after_seconds
            if wait_sec is None or wait_sec <= 0:
                wait_sec = 1.0
            wait_sec = min(float(wait_sec), float(cap_sleep_seconds))
            logger.warning(
                "%s: rate limit, sleep %.1fs (attempt %s/%s)",
                operation_label,
                wait_sec,
                attempt + 1,
                limit,
            )
            await asyncio.sleep(wait_sec)
            attempt += 1

    assert last_error is not None
    raise TelegramTelethonError(
        f"Исчерпаны попытки после FloodWait для {operation_label}",
    ) from last_error
