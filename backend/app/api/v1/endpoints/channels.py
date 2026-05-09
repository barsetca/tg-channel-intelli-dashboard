from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_channel_service
from app.schemas.channel import (
    ChannelCollectRequest,
    ChannelCollectResponse,
    ChannelCreate,
    ChannelCreateResult,
    ChannelListResponse,
)
from app.services.channel_service import ChannelService

router = APIRouter()


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ChannelService = Depends(get_channel_service),
) -> ChannelListResponse:
    return await service.list_channels(limit=limit, offset=offset)


@router.post("", response_model=ChannelCreateResult)
async def create_channel(
    body: ChannelCreate,
    service: ChannelService = Depends(get_channel_service),
) -> ChannelCreateResult:
    return await service.create_or_get(body)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    service: ChannelService = Depends(get_channel_service),
) -> None:
    ok = await service.delete_channel(channel_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")


@router.post("/{channel_id}/collect", response_model=ChannelCollectResponse)
async def collect_channel(
    channel_id: int,
    body: ChannelCollectRequest,
    service: ChannelService = Depends(get_channel_service),
) -> ChannelCollectResponse:
    out = await service.collect_channel(channel_id, body)
    if out.status == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=out.message)
    if out.status == "failed_upstream":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=out.message)
    if out.status == "failed_internal":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=out.message)
    return out
