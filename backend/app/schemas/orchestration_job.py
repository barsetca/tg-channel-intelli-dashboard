"""Статус фонового задания оркестратора для UI и отладки."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrchestrationJobStatus(BaseModel):
    job_id: str
    kind: str
    status: str = Field(..., description="queued | running | completed | failed")
    detail: str = Field("", description="Текущее пояснение или сообщение об ошибке")
    stage: str | None = Field(None, description="Идентификатор текущего этапа (пока job running)")
    stage_label: str | None = Field(None, description="Человекочитаемое имя этапа")
    created_at: datetime
    updated_at: datetime
