"""Семантический поиск по Qdrant (`POST /semantic-search`) — сценарий 4."""

from fastapi import APIRouter, Depends

from app.api.deps import get_vector_service
from app.schemas.intelligence import (
    SemanticSearchHit,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.services.vector_service import VectorService

router = APIRouter()


@router.post(
    "",
    response_model=SemanticSearchResponse,
    summary="Семантический поиск",
    description=(
        "Эмбеддинг запроса + поиск в Qdrant. Поле `synthesis_placeholder` зарезервировано под "
        "LLM-ответ по сниппетам (RAG)."
    ),
)
async def semantic_search(
    body: SemanticSearchRequest,
    vector: VectorService = Depends(get_vector_service),
) -> SemanticSearchResponse:
    raw = await vector.semantic_search(
        query=body.query,
        limit=body.limit,
        content_type=body.content_type,
        channel_id=body.channel_id,
    )
    hits: list[SemanticSearchHit] = []
    for h in raw:
        p = h.properties
        text = p.get("text")
        hits.append(
            SemanticSearchHit(
                point_id=h.point_id,
                score=h.score,
                channel_id=p.get("channel_id"),
                post_id=p.get("post_id"),
                content_type=p.get("content_type"),
                text_preview=(str(text)[:400] + "…") if text and len(str(text)) > 400 else text,
            ),
        )
    return SemanticSearchResponse(
        query=body.query,
        hits=hits,
        synthesis_placeholder=None,
    )
