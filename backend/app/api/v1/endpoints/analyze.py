"""Запуск AI-анализа канала (`POST /analyze/{id}`) — сценарий 2."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import AnalyzeChannelRequest, AnalyzeChannelResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter()

_DEFAULT_ANALYZE_INTENT = (
    "Проанализируй канал: тематика, стиль, риски и рекомендации для рекламодателя."
)


@router.post(
    "/{channel_id}",
    response_model=AnalyzeChannelResponse,
    summary="Анализировать канал",
    description=(
        "Запускает `ChannelAnalysisPipeline`, сохраняет результат в таблицу `analyses`. "
        "При блокировке валидации статус `blocked_validation` (см. также глобальный handler 422)."
    ),
    responses={
        404: {"description": "Канал не найден"},
        422: {"description": "Pipeline validation block (если исключение проброшено наружу)"},
    },
)
async def analyze_channel(
    channel_id: int,
    body: AnalyzeChannelRequest | None = None,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> AnalyzeChannelResponse:
    intent = (body.user_intent if body else None) or _DEFAULT_ANALYZE_INTENT
    result, err = await svc.run_channel_analysis(channel_id=channel_id, user_intent=intent)
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    assert result is not None
    return result
