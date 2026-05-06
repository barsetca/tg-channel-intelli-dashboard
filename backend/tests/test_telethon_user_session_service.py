"""Юнит-тесты сервиса Telethon без реального клиента Telegram."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.errors import FloodWaitError
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel, ChatPhotoEmpty, Message, PeerChannel

from app.core.config import Settings
from app.integrations.telethon.exceptions import (
    TelegramAuthRequiredError,
    TelegramInvalidIdentifierError,
    TelegramTelethonError,
)
from app.integrations.telethon.user_session_service import TelethonUserSessionService


def _test_settings(**overrides: object) -> Settings:
    data: dict[str, object] = {
        "telegram_api_id": 1,
        "telegram_api_hash": "hash",
        "telegram_session_dir": ".",
        "telegram_session_name": "sess",
        "telegram_flood_max_wait_seconds": 600,
        "telegram_flood_retry_attempts": 5,
        "database_url": "sqlite+aiosqlite:///./tests.db",
    }
    data.update(overrides)
    return Settings(**data)  # type: ignore[arg-type]


def _channel(*, cid: int, username: str | None = "news", mega: bool = False) -> Channel:
    """Минимальный валидный Channel для объектов chats в SearchRequest."""
    return Channel(
        id=cid,
        title="Тест",
        photo=ChatPhotoEmpty(),
        date=datetime.now(timezone.utc),
        broadcast=not mega,
        megagroup=mega,
        username=username,
    )


class FakeSearchClient:
    """
    Заглушка клиента: синхронный ``is_connected``
    и асинхронный вызов вида ``await client(SearchRequest(...) )``.
    """

    def __init__(self, chats):
        self._chats = chats

    def is_connected(self) -> bool:
        return True

    async def __call__(self, request):
        if isinstance(request, SearchRequest):
            return SimpleNamespace(chats=self._chats)
        raise AssertionError(f"unexpected request {type(request)}")


class FakeResolveClient:
    def is_connected(self) -> bool:
        return True

    async def get_entity(self, handle):
        # Не канал Telethon-слоя → resolve_channel обязан отказать доменным исключением.
        return object()


class FakeResolveLeftPublicClient:
    def is_connected(self) -> bool:
        return True

    async def get_entity(self, handle):
        _ = handle
        ch = _channel(cid=42, username="public_channel")
        ch.left = True
        return ch


def test_msg_to_brief_normalizes_naive_datetime() -> None:
    naive = datetime(2024, 1, 2, 3, 4, 5)
    msg = Message(
        id=7,
        peer_id=PeerChannel(channel_id=1),
        date=naive,
        message="Привет",
        views=100,
        forwards=5,
    )
    brief = TelethonUserSessionService._msg_to_brief(msg)
    assert brief.telegram_message_id == 7
    assert brief.views == 100
    assert brief.text == "Привет"
    assert brief.date_utc.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_search_public_channels_skips_megagroup_when_requested() -> None:
    svc = TelethonUserSessionService(settings=_test_settings())
    mega = _channel(cid=2, mega=True)
    bc = _channel(cid=3, mega=False)

    async def guarded(label: str, factory):
        return await factory()

    svc._guarded_call = guarded  # type: ignore[method-assign]
    svc._client = FakeSearchClient([mega, bc])

    hits = await svc.search_public_channels("q", limit=10, broadcast_only=True)
    assert len(hits) == 1
    assert hits[0].telegram_channel_id == 3


@pytest.mark.asyncio
async def test_resolve_channel_raises_if_not_channel() -> None:
    svc = TelethonUserSessionService(settings=_test_settings())

    async def guarded(label: str, factory):
        maybe = factory()
        return await maybe

    svc._guarded_call = guarded  # type: ignore[method-assign]
    svc._client = FakeResolveClient()

    with pytest.raises(TelegramInvalidIdentifierError):
        await svc.resolve_channel("@some")


@pytest.mark.asyncio
async def test_resolve_channel_allows_left_public_username() -> None:
    svc = TelethonUserSessionService(settings=_test_settings())

    async def guarded(label: str, factory):
        maybe = factory()
        return await maybe

    svc._guarded_call = guarded  # type: ignore[method-assign]
    svc._client = FakeResolveLeftPublicClient()

    ch = await svc.resolve_channel("@public_channel")
    assert isinstance(ch, Channel)
    assert ch.username == "public_channel"


@pytest.mark.asyncio
async def test_connected_guard_raises_when_no_client() -> None:
    svc = TelethonUserSessionService(settings=_test_settings())
    svc._client = None
    with pytest.raises(TelegramAuthRequiredError, match="Сессия не авторизована"):
        await svc.search_public_channels("x")


@pytest.mark.asyncio
async def test_guarded_call_flood_retries_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = TelethonUserSessionService(settings=_test_settings(telegram_flood_retry_attempts=2))

    cli = MagicMock()
    cli.is_connected.return_value = True
    cli.is_user_authorized = AsyncMock(return_value=True)
    svc._client = cli

    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise FloodWaitError(None, 1)
        return "ok"

    import asyncio

    sleeps: list[float] = []

    async def track_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", track_sleep)

    out = await svc._guarded_call("probe", flaky)
    assert out == "ok"
    assert sleeps, "ожидался sleep после FloodWait"
