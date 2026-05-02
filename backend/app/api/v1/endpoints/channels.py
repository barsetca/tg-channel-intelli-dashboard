from fastapi import APIRouter, Depends, Query

from app.api.deps import get_channel_service
from app.schemas.channel import ChannelCreate, ChannelRead
from app.services.channel_service import ChannelService

router = APIRouter()


@router.get("", response_model=list[ChannelRead])
async def list_channels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ChannelService = Depends(get_channel_service),
) -> list[ChannelRead]:
    return await service.list_channels(limit=limit, offset=offset)


@router.post("", response_model=ChannelRead)
async def create_channel(
    body: ChannelCreate,
    service: ChannelService = Depends(get_channel_service),
) -> ChannelRead:
    return await service.create_or_get(body)
