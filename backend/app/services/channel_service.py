from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.repositories.channel_repository import ChannelRepository
from app.schemas.channel import ChannelCreate, ChannelRead


class ChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._channels = ChannelRepository(session)

    async def create_or_get(self, data: ChannelCreate) -> ChannelRead:
        existing = await self._channels.get_by_telegram_id(data.telegram_id)
        if existing:
            return ChannelRead.model_validate(existing)

        channel = Channel(
            telegram_id=data.telegram_id,
            username=data.username,
            title=data.title,
            description=data.description,
        )
        await self._channels.add(channel)
        await self._session.commit()
        return ChannelRead.model_validate(channel)

    async def list_channels(self, limit: int = 50, offset: int = 0) -> list[ChannelRead]:
        rows = await self._channels.list_all(limit=limit, offset=offset)
        return [ChannelRead.model_validate(r) for r in rows]
