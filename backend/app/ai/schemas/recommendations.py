"""Выход Recommendation-стадии до маппинга в ORM `Recommendation`."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendationItem(BaseModel):
    """Одна рекомендация: потом превращается в строку `recommendations`."""

    recommendation_type: str = Field(max_length=96)
    headline: str = Field(max_length=512)
    body: str
    relevance_hint: float = Field(
        ge=0.0,
        le=1.0,
        description="Подсказка релевантности (потом Decimal в БД).",
    )


class RecommendationsBundle(BaseModel):
    """Корневая модель для `parse` / `model_validate_json`."""

    items: list[RecommendationItem] = Field(default_factory=list)
