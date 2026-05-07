"""Запуск AI-анализа канала (`POST /analyze/{id}`) — сценарий 2."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_intelligence_service
from app.integrations.telethon.exceptions import TelegramTelethonError
from app.schemas.intelligence import (
    AnalyzeChannelByHandleRequest,
    AnalyzeChannelRequest,
    AnalyzeChannelResponse,
    SummarizePostsByHandleRequest,
    SummarizePostsResponse,
)
from app.services.intelligence_service import IntelligenceService

router = APIRouter()

_DEFAULT_ANALYZE_INTENT = (
    "Проанализируй канал: тематика, стиль, риски и рекомендации для рекламодателя."
)


@router.post(
    "/by-handle",
    response_model=AnalyzeChannelResponse,
    summary="Анализировать канал по ссылке/username",
    description=(
        "Сценарий 2: проверяет доступность канала через Telethon, подтягивает последние посты, "
        "запускает AI-анализ и сохраняет результат в таблицу `analyses`."
    ),
)
async def analyze_channel_by_handle(
    body: AnalyzeChannelByHandleRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> AnalyzeChannelResponse:
    return await svc.run_channel_analysis_by_handle(body=body)


@router.post(
    "/by-handle/summarize",
    response_model=SummarizePostsResponse,
    summary="Сводка последних постов по ссылке/username",
    description="Сценарий 3: получает посты через Telethon, строит постовые и оконную сводки, сохраняет в Qdrant.",
)
async def summarize_channel_by_handle(
    body: SummarizePostsByHandleRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> SummarizePostsResponse:
    try:
        return await svc.summarize_recent_posts_by_handle(body=body)
    except TelegramTelethonError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


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
    post_limit = (body.post_limit if body else 10)
    result, err = await svc.run_channel_analysis(channel_id=channel_id, user_intent=intent, post_limit=post_limit)
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Канал не найден")
    assert result is not None
    return result
