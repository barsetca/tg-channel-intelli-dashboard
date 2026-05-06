from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExtraConditionsReviewOutput(BaseModel):
    """Проверка доп. условий: противоречия + применимые фильтры."""

    needs_review: bool = Field(False, description="Нужна ручная проверка/уточнение")
    reason: str = Field("", description="Причина manual review")
    # Если в extra_conditions есть условие вида "с последним постом не позднее ...",
    # LLM возвращает верхнюю границу last_post_at.
    last_post_at_lte: datetime | None = Field(
        None,
        description="Верхняя граница даты последнего поста (<=)",
    )
