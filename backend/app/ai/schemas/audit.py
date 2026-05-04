"""Структурированный артефакт аудита канала (стадия Structured JSON)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelAuditArtifact(BaseModel):
    """Итоговый JSON для сохранения в `Analysis.result_json` (или вложение внутрь обёртки)."""

    overall_score: float = Field(ge=0.0, le=10.0, description="Обобщённая оценка 0..10")
    strengths: list[str] = Field(default_factory=list, description="Сильные стороны канала")
    risks: list[str] = Field(default_factory=list, description="Риски / слабые места")
    summary: str = Field(description="Краткое текстовое резюме для карточки")
