"""ORM: журнал запросов semantic / гибридного поиска (аудит, UX, отладка)."""

from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin


class SearchRun(Base, TimestampMixin):
    """
    Один пользовательский (или автоматический) запуск поиска.
    Вектора хранятся в Qdrant; здесь — текст запроса, фильтры, метрики и ошибки.
    """

    __tablename__ = "search_runs"
    __table_args__ = (
        Index("ix_search_runs_created_at_desc", "created_at"),
        Index("ix_search_runs_normalized_query_hash", "normalized_query_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    query_text: Mapped[str] = mapped_column(Text(), nullable=False)
    # Нормализованный текст или хеш для группировки в аналитике популярных запросов
    normalized_query_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    filters_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    top_result_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # Ответ после LLM synthesis (сценарий 4) и воспроизводимость источников
    answer_synthesis_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    retrieved_sources_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    error_text: Mapped[str | None] = mapped_column(Text(), nullable=True)

    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="search_run",
        foreign_keys="[Recommendation.search_run_id]",
    )
