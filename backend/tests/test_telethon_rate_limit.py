"""Тесты ретраев при FloodWait (без реального доступа к сети)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from telethon.errors import FloodWaitError

from app.integrations.telethon.exceptions import TelegramTelethonError
from app.integrations.telethon.rate_limit import run_with_optional_flood_retry


@pytest.mark.asyncio
async def test_success_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeper = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleeper)

    async def op() -> str:
        return "ok"

    out = await run_with_optional_flood_retry(
        op,
        max_additional_attempts=2,
        cap_sleep_seconds=999,
        operation_label="t",
    )
    assert out == "ok"
    sleeper.assert_not_awaited()


@pytest.mark.asyncio
async def test_retries_after_flood_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeper = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleeper)

    calls: list[int] = []

    async def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise FloodWaitError(None, 6000)  # кап ограничит фактический sleep до 30
        return "done"

    out = await run_with_optional_flood_retry(
        flaky,
        max_additional_attempts=2,
        cap_sleep_seconds=30,
        operation_label="t",
    )
    assert out == "done"
    assert len(calls) == 2
    sleeper.assert_awaited_once()
    waited = sleeper.call_args[0][0]
    assert waited == 30.0


@pytest.mark.asyncio
async def test_raises_after_retries_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def always_flood() -> str:
        raise FloodWaitError(None, 1)

    with pytest.raises(TelegramTelethonError):
        await run_with_optional_flood_retry(
            always_flood,
            max_additional_attempts=1,
            cap_sleep_seconds=10,
            operation_label="t",
        )


@pytest.mark.asyncio
async def test_non_rate_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def boom() -> str:
        raise ValueError("not flood")

    with pytest.raises(ValueError, match="not flood"):
        await run_with_optional_flood_retry(
            boom,
            max_additional_attempts=2,
            cap_sleep_seconds=10,
            operation_label="t",
        )
