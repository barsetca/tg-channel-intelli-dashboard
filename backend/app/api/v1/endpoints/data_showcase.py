"""Витрина данных (`GET /data-showcase`) — отдельная фича отображения нормализованных records."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import DataShowcaseResponse
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.get(
    "",
    response_model=DataShowcaseResponse,
    summary="Витрина данных",
    description="Показывает строки нормализованных records (snapshot_json) с временем сбора и источником.",
)
async def get_data_showcase(
    limit: int = Query(100, ge=1, le=500),
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> DataShowcaseResponse:
    return await svc.get_data_showcase(limit=limit)


@router.get(
    "/export",
    summary="Экспорт витрины данных",
    description="Скачивание JSON/CSV из витрины данных с ограничением limit.",
    response_class=Response,
)
async def export_data_showcase(
    export_format: Literal["json", "csv"] = Query(
        "json",
        alias="format",
        description="json или csv",
    ),
    limit: int = Query(100, ge=1, le=500),
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> Response:
    rows = await svc.export_data_showcase_payload(limit=limit)
    if export_format == "csv":
        payload = svc.channels_to_csv(rows)
        return Response(
            content=payload.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="data_showcase_export.csv"'},
        )
    body = svc.channels_to_json_bytes(rows)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="data_showcase_export.json"'},
    )
