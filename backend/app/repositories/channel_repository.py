from collections.abc import Sequence

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.repositories.base import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Channel)

    async def get_by_telegram_id(self, telegram_id: int) -> Channel | None:
        result = await self._session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def search_catalog(
        self,
        *,
        topic: str,
        limit: int,
        min_subscribers: int | None = None,
        max_subscribers: int | None = None,
        language: str | None = None,
        region_country: str | None = None,
        new_only: bool = False,
    ) -> list[Channel]:
        """
        Поиск по локальной БД (сценарий 1, шаг «каталог»).
        Тематика — по полям title / description / primary_topic.
        """
        pattern = f"%{topic.strip()}%"
        stmt = select(Channel).where(
            or_(
                Channel.primary_topic.ilike(pattern),
                Channel.title.ilike(pattern),
                Channel.description.ilike(pattern),
            )
        )
        if min_subscribers is not None:
            stmt = stmt.where(
                (Channel.subscriber_count.is_not(None)) & (Channel.subscriber_count >= min_subscribers)
            )
        if max_subscribers is not None:
            stmt = stmt.where(
                (Channel.subscriber_count.is_not(None)) & (Channel.subscriber_count <= max_subscribers)
            )
        if language:
            stmt = stmt.where(Channel.language_hint == language)
        if region_country:
            stmt = stmt.where(Channel.region_country == region_country)
        if new_only:
            # «Новые» — эвристика: ни разу не синхронизировали (last_sync_at пустой)
            stmt = stmt.where(Channel.last_sync_at.is_(None))
        stmt = stmt.order_by(desc(Channel.subscriber_count).nulls_last(), desc(Channel.id))
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def existing_telegram_ids_among(self, telegram_ids: Sequence[int]) -> set[int]:
        """Множество telegram_id, которые уже есть в каталоге (для new_only)."""
        ids = list({int(x) for x in telegram_ids})
        if not ids:
            return set()
        result = await self._session.execute(select(Channel.telegram_id).where(Channel.telegram_id.in_(ids)))
        return {int(x) for x in result.scalars().all()}

    async def upsert_discovery_channel(
        self,
        *,
        telegram_id: int,
        username: str | None,
        title: str | None,
        description: str | None,
        subscriber_count: int | None,
        invite_slug: str | None,
        primary_topic: str | None,
        language_hint: str | None,
        region_country: str | None,
    ) -> Channel:
        """Создать или обновить канал по результатам discovery (сценарий 1)."""
        existing = await self.get_by_telegram_id(telegram_id)
        if existing is not None:
            if username is not None:
                existing.username = username
            if title is not None:
                existing.title = title
            if description is not None:
                existing.description = description
            if subscriber_count is not None:
                existing.subscriber_count = subscriber_count
            if invite_slug is not None:
                existing.invite_slug = invite_slug
            if primary_topic is not None:
                existing.primary_topic = primary_topic
            if language_hint is not None:
                existing.language_hint = language_hint
            if region_country is not None:
                existing.region_country = region_country
            existing.sync_status = "discovered"
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        ch = Channel(
            telegram_id=telegram_id,
            username=username,
            title=title,
            description=description,
            subscriber_count=subscriber_count,
            invite_slug=invite_slug,
            primary_topic=primary_topic,
            language_hint=language_hint,
            region_country=region_country,
            sync_status="discovered",
            is_public_accessible=True,
        )
        return await self.add(ch)
