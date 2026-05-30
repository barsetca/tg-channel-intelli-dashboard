"""История отчётов анализа канала (сценарий 2): список, повторное чтение и удаление."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import get_intelligence_service
from app.schemas.intelligence import (
    ChannelAnalysisHistoryItem,
    SavedChannelAnalysisDetail,
)
from app.services.channel_analysis_pdf import build_channel_analysis_pdf, channel_analysis_pdf_filename
from app.services.intelligence_service import IntelligenceService

router = APIRouter()


@router.get(
    "",
    response_model=list[ChannelAnalysisHistoryItem],
    summary="Список сохранённых анализов каналов",
)
async def list_channel_analyses(
    channel_id: int | None = Query(
        None,
        description="Фильтр по id канала в каталоге; без фильтра — последние записи",
    ),
    limit: int = Query(50, ge=1, le=100),
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> list[ChannelAnalysisHistoryItem]:
    return await svc.list_channel_analysis_history(channel_id=channel_id, limit=limit)


@router.get(
    "/{analysis_id}",
    response_model=SavedChannelAnalysisDetail,
    summary="Сохранённый отчёт анализа по id записи analyses",
)
async def get_channel_analysis_detail(
    analysis_id: int,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> SavedChannelAnalysisDetail:
    row, err = await svc.get_saved_channel_analysis(
        analysis_id=analysis_id,
        lightweight=True,
    )
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Анализ не найден")
    if err == "channel_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Канал для этого анализа не найден в каталоге",
        )
    assert row is not None
    return row


@router.get(
    "/{analysis_id}/pdf",
    summary="PDF отчёта анализа (inline в браузере)",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF-документ без сохранения на сервере",
        }
    },
)
async def get_channel_analysis_pdf(
    analysis_id: int,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> Response:
    row, err = await svc.get_saved_channel_analysis(
        analysis_id=analysis_id,
        lightweight=True,
    )
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Анализ не найден")
    if err == "channel_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Канал для этого анализа не найден в каталоге",
        )
    assert row is not None
    if row.report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Отчёт не содержит данных для экспорта",
        )
    try:
        pdf_bytes = build_channel_analysis_pdf(
            report=row.report,
            channel_label=(row.channel_display_ref or "").strip() or f"#{row.channel_id}",
            channel_id=row.channel_id,
            analysis_id=row.analysis_id,
            status=row.status,
            message=row.message,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    filename = channel_analysis_pdf_filename(
        channel_display_ref=row.channel_display_ref,
        channel_id=row.channel_id,
        analysis_id=row.analysis_id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete(
    "/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сохранённый отчёт анализа",
)
async def delete_channel_analysis(
    analysis_id: int,
    svc: IntelligenceService = Depends(get_intelligence_service),
) -> None:
    _ok, err = await svc.delete_channel_analysis(analysis_id=analysis_id)
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Анализ не найден")
