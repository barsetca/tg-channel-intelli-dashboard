"""Входной контекст стадий: факты о канале и постах до вызовов LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PostSnippet:
    """Минимальный срез поста для ContextBuilder (можно собрать из ORM `Post`)."""

    posted_at: datetime
    text: str | None
    views: int | None = None


@dataclass
class ContextBundle:
    """
    Пакет данных для Planner / Summarization.
    `combined_posts_text` — склеенный текст с маркерами дат (уже обрезанный политикой длины).
    """

    analyzer_id: str
    prompt_version: str
    user_intent: str
    channel_title: str | None
    channel_username: str | None
    combined_posts_text: str
    post_count: int
    # Оценка достаточности данных 0..1 по простым правилам (не self-report LLM)
    data_sufficiency: float
    metrics_text: str | None = None
    # Фрагменты из RAG (если оркестратор вызвал vector_search до/после плана)
    rag_snippets: list[str] = field(default_factory=list)
