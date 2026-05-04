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
