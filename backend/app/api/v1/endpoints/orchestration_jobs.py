"""Чтение статуса фоновых заданий (после POST /search-channels с telegram_live)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.orchestration.coordinator import OrchestrationCoordinator
from app.schemas.orchestration_job import OrchestrationJobStatus

router = APIRouter()


def _coordinator(request: Request) -> OrchestrationCoordinator:
    coord = getattr(request.app.state, "orchestration_coordinator", None)
    if coord is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OrchestrationCoordinator не смонтирован.",
        )
    return coord


@router.get(
    "/jobs/{job_id}",
    response_model=OrchestrationJobStatus,
    summary="Статус фонового задания",
    description="Опрашивайте после telegram live search, пока status не станет completed или failed.",
)
async def get_orchestration_job_status(job_id: str, request: Request) -> OrchestrationJobStatus:
    coord = _coordinator(request)
    job = coord.get_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Задание не найдено (устарело или другой процесс воркера).")
    return OrchestrationJobStatus(
        job_id=job.id,
        kind=job.kind.value,
        status=job.status.value,
        detail=job.detail,
        stage=job.stage,
        stage_label=job.stage_label,
        planner_output=job.planner_output,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=OrchestrationJobStatus,
    summary="Отмена фонового задания",
)
async def cancel_orchestration_job(job_id: str, request: Request) -> OrchestrationJobStatus:
    coord = _coordinator(request)
    job = coord.cancel_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Задание не найдено (устарело или другой процесс воркера).")
    return OrchestrationJobStatus(
        job_id=job.id,
        kind=job.kind.value,
        status=job.status.value,
        detail=job.detail,
        stage=job.stage,
        stage_label=job.stage_label,
        planner_output=job.planner_output,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
