"""Выход AI Planner для сценария 1 (поиск каналов)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchPlannerOutput(BaseModel):
    """Структурированный запрос после шага LLM (или fallback без OpenAI)."""

    search_topic: str = Field(..., min_length=1, description="Тема/ниша для поиска в каталоге или Telegram")
    min_subscribers: int | None = Field(None, ge=0, description="Мин. подписчиков (после слияния с формой)")
    max_subscribers: int | None = Field(None, ge=0, description="Макс. подписчиков")
    count: int = Field(20, ge=1, le=100, description="Желаемое число каналов в выдаче")
    language: str | None = Field(None, max_length=32)
    region_country: str | None = Field(None, max_length=128)
    confidence: Literal["high", "medium", "low"] = Field(
        "medium",
        description="Самооценка планировщика (логи / audit)",
    )
