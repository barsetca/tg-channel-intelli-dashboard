"""Сравнение каналов (`POST /channels/compare`) — сценарий 5."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import CompareChannelsRequest, CompareChannelsResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.post(
    "/compare",
    response_model=CompareChannelsResponse,
    summary="Сравнить каналы",
    description=(
        "2–5 каналов: метрики из БД; текстовые выводы — шаблон (позже через LLM)."
    ),
    responses={404: {"description": "Один из channel_ids не найден"}},
)
async def compare_channels(
    body: CompareChannelsRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> CompareChannelsResponse:
    result = await svc.compare_channels(body)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Один или несколько каналов не найдены",
        )
    return result
