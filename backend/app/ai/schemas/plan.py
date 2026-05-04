"""Схема выхода LLM Planner — строгая валидация через Pydantic + (по возможности) OpenAI parse."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """
    Машиночитаемый план: оркестратор читает флаги и решает, вызывать ли RAG/Qdrant tool.
    Поля на английском — стабильнее для prompt + JSON модели.
    """

    steps: list[str] = Field(
        default_factory=list,
        description="Краткие шаги, которые предлагает модель (для логов и UI).",
    )
    use_rag: bool = Field(
        default=False,
        description="Нужен ли semantic retrieval (Qdrant) для этого запроса.",
    )
    focus_topics: list[str] = Field(
        default_factory=list,
        description="Темы, на которых настаивает пользователь / модель.",
    )
    max_posts_to_cite: int = Field(
        default=20,
        ge=1,
        le=500,
        description="Верхняя граница числа постов, релевантных для итогового отчёта.",
    )
    plan_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Самооценка планировщика (низкий вес в aggregate confidence).",
    )
