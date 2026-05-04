"""Похожие каналы (`GET /recommendations/{id}`) — сценарий 6."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_intelligence_service, get_vector_service
from app.schemas.intelligence import SimilarChannelsResponse
from app.services.intelligence_service import IntelligenceService
from app.services.vector_service import VectorService

router = APIRouter()


@router.get(
    "/{channel_id}",
    response_model=SimilarChannelsResponse,
    summary="Похожие каналы",
    description="Профиль канала в embedding, поиск по постам, агрегация по channel_id.",
    responses={404: {"description": "Канал не найден"}},
)
async def similar_channels(
    channel_id: int,
    limit: int = Query(10, ge=1, le=50),
    svc: IntelligenceService = Depends(get_intelligence_service),
    vector: VectorService = Depends(get_vector_service),
) -> SimilarChannelsResponse:
    result, err = await svc.find_similar_channels(
        seed_channel_id=channel_id,
        vector=vector,
        limit=limit,
    )
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    assert result is not None
    return result
