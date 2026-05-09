from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.channel import Channel
from app.repositories.channel_repository import ChannelRepository


@pytest.mark.asyncio
async def test_upsert_discovery_updates_existing_draft_by_username() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
                await conn.run_sync(Channel.__table__.create)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            repo = ChannelRepository(session)

            draft = Channel(
                telegram_id=111_111_111,
                username="test_channel",
                title="@test_channel",
                sync_status="draft",
                topic_search="old topic",
                last_sync_at=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(draft)
            await session.commit()
            await session.refresh(draft)

            updated = await repo.upsert_discovery_channel(
                telegram_id=222_222_222,
                username="test_channel",
                title="Real title",
                description="updated from discovery",
                subscriber_count=12345,
                invite_slug="test_channel",
                primary_topic="finance",
                topic_search="finance channels",
                language_hint="ru",
                region_country="KZ",
            )
            await session.commit()

            assert int(updated.id) == int(draft.id)
            assert updated.telegram_id == 222_222_222
            assert updated.username == "test_channel"
            assert updated.title == "Real title"
            assert updated.sync_status == "discovered"
            assert updated.last_sync_at is not None

            total = int((await session.execute(select(func.count()).select_from(Channel))).scalar_one())
            assert total == 1
    finally:
        await engine.dispose()
