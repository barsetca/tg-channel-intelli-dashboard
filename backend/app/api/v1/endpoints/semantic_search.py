"""Семантический поиск (`POST /semantic-search`) — сценарий 4."""

from fastapi import APIRouter, Depends

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import (
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.post(
    "",
    response_model=SemanticSearchResponse,
    summary="Семантический поиск",
    description="Intent routing + retrieval + aggregation + grounded synthesis с review-first политикой.",
)
async def semantic_search(
    body: SemanticSearchRequest,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> SemanticSearchResponse:
    return await svc.semantic_search_scenario4(body)
