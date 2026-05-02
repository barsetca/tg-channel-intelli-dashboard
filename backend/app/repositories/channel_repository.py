from sqlalchemy import select
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
