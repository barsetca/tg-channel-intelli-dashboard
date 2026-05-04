"""Один канал: детали (GET) и сводка постов (POST) — сценарии 2 и 3."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import ChannelDetail, SummarizePostsRequest, SummarizePostsResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.post(
    "/{channel_id}/summarize",
    response_model=SummarizePostsResponse,
    summary="Сводка последних постов",
    description="Сценарий 3: chunking + LLM summarization по последним N постам канала.",
)
async def summarize_channel_posts(
    channel_id: int,
    body: SummarizePostsRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> SummarizePostsResponse:
    result, err = await svc.summarize_recent_posts(channel_id=channel_id, body=body)
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    assert result is not None
    return result


@router.get(
    "/{channel_id}",
    response_model=ChannelDetail,
    summary="Карточка канала",
    description="Сценарий 2 (часть): метаданные канала из БД для UI.",
    responses={404: {"description": "Канал с таким id не существует"}},
)
async def get_channel(
    channel_id: int,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> ChannelDetail:
    row = await svc.get_channel_detail(channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    return row
