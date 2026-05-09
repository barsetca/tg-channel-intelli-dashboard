"""Очередь оркестратора: полный telegram discovery с поддельным Telethon."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.integrations.telethon.dto import TelegramChannelFullInfo, TelegramPostBrief, TelegramSearchHit
from app.orchestration.coordinator import JobStatus, OrchestrationCoordinator


class _FakeTelethon:
    """Без реального MTProto: один «канал» и два поста для метрик."""

    def __init__(self) -> None:
        self._tid = -1009998887776

    async def search_public_channels(
        self,
        query: str,
        *,
        limit: int = 15,
        broadcast_only: bool = True,
    ) -> list[TelegramSearchHit]:
        _ = query, limit, broadcast_only
        return [
            TelegramSearchHit(
                telegram_channel_id=self._tid,
                username="orchestration_fake_channel",
                title="Orchestration Fake",
                is_broadcast=True,
                is_megagroup=False,
            )
        ]

    async def get_channel_info(self, identifier: str | int) -> TelegramChannelFullInfo:
        _ = identifier
        return TelegramChannelFullInfo(
            telegram_channel_id=self._tid,
            username="orchestration_fake_channel",
            title="Orchestration Fake",
            about="Тестовый канал пайплайна.",
            participants_count=12500,
            is_broadcast=True,
        )

    async def fetch_recent_posts(
        self,
        identifier: str | int,
        *,
        limit: int = 25,
        max_additional_fetch_rounds_for_flood: int = 0,
    ) -> list[TelegramPostBrief]:
        _ = identifier, max_additional_fetch_rounds_for_flood
        now = datetime.now(timezone.utc)
        return [
            TelegramPostBrief(
                telegram_message_id=1,
                date_utc=now - timedelta(days=14),
                text="hello",
            ),
            TelegramPostBrief(telegram_message_id=2, date_utc=now - timedelta(days=1), text="world"),
        ]


@pytest.mark.asyncio
async def test_telegram_discovery_job_reaches_completed(tmp_path) -> None:
    _ = tmp_path
    s = get_settings().model_copy(update={"openai_api_key": None})
    coord = OrchestrationCoordinator(settings=s, get_telegram=lambda: _FakeTelethon())
    await coord.start()
    try:
        jid = await coord.schedule_telegram_channel_discovery(payload={"topic": "unit test niche", "count": 3})
        for _ in range(200):
            job = coord.get_job(jid)
            assert job is not None
            if job.status == JobStatus.COMPLETED:
                break
            if job.status == JobStatus.FAILED:
                detail = (job.detail or "").lower()
                if "readonly database" in detail or "no such table" in detail:
                    pytest.skip("SQLite окружение не готово для записи/схемы, пропускаем интеграционный тест оркестрации.")
            await asyncio.sleep(0.03)
        else:
            pytest.fail("job did not complete in time")

        final = coord.get_job(jid)
        assert final is not None
        assert final.status == JobStatus.COMPLETED
        assert final.planner_output is not None
        assert "search_topic" in final.planner_output
    finally:
        await coord.stop()
