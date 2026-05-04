"""Экспорт данных (`GET /export`) — сценарий 7."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_intelligence_service
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.get(
    "",
    summary="Экспорт каналов",
    description="Скачивание JSON или CSV по накопленным каналам в БД.",
    response_class=Response,
)
async def export_channels(
    export_format: Literal["json", "csv"] = Query(
        "json",
        alias="format",
        description="json или csv",
    ),
    limit: int = Query(500, ge=1, le=5000),
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> Response:
    rows = await svc.export_channels_payload(limit=limit)
    if export_format == "csv":
        payload = svc.channels_to_csv(rows)
        return Response(
            content=payload.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="channels_export.csv"'},
        )
    body = svc.channels_to_json_bytes(rows)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="channels_export.json"'},
    )
