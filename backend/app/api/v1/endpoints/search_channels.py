"""Сценарий 1 + 8: поиск каналов по фильтрам (`POST /search-channels`)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import SearchChannelsRequest, SearchChannelsResponse, SearchTopicOptionsResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.post(
    "",
    response_model=SearchChannelsResponse,
    summary="Поиск каналов",
    description=(
        "Возвращает список карточек из локального каталога (SQLite) или флаг manual_review, "
        "если запрос слишком общий (сценарий 8)."
    ),
)
async def search_channels(
    body: SearchChannelsRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> SearchChannelsResponse:
    return await svc.search_channels(body)


@router.get(
    "/topics",
    response_model=SearchTopicOptionsResponse,
    summary="Справочник тем/ниш",
    description="Возвращает уникальные значения поля topic_search из сохранённых каналов.",
)
async def search_topic_options(
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> SearchTopicOptionsResponse:
    return await svc.list_search_topic_options()
