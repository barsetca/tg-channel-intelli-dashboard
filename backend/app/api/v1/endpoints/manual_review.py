from __future__ import annotations

from typing import Literal

from fastapi import Response
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import ManualReviewJournalResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter(tags=["manual-review"])


@router.get("", response_model=ManualReviewJournalResponse)
async def get_manual_review_journal(
    limit: int = Query(default=100, ge=1, le=500),
    source: str = Query(default="all"),
    service: IntelligenceService = Depends(get_intelligence_service),
) -> ManualReviewJournalResponse:
    return await service.get_manual_review_journal(limit=limit, source_filter=source)


@router.get("/export", response_class=Response)
async def export_manual_review_journal(
    export_format: Literal["json", "csv"] = Query("json", alias="format"),
    source: str = Query(default="all"),
    limit: int = Query(default=100, ge=1, le=500),
    service: IntelligenceService = Depends(get_intelligence_service),
) -> Response:
    rows = await service.export_manual_review_payload(limit=limit, source_filter=source)
    if export_format == "csv":
        payload = service.channels_to_csv(rows)
        return Response(
            content=payload.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="manual_review_export.csv"'},
        )
    body = service.channels_to_json_bytes(rows)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="manual_review_export.json"'},
    )
