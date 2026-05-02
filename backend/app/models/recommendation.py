"""ORM: рекомендации пользователю (канал к мониторингу, темы, действия после анализа/поиска)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.channel import Channel
    from app.models.search_run import SearchRun


class Recommendation(Base, TimestampMixin):
    """
    Может порождаться из анализа и/или сессии поиска (оба FK опциональны — гибкий сценарий).
    payload_json — машинная структура; headline/body — готовые части под UI.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_kind_score", "recommendation_type", "relevance_score"),
        Index("ix_recommendations_analysis", "source_analysis_id"),
        Index("ix_recommendations_search_run", "search_run_id"),
        Index("ix_recommendations_seed_channel", "seed_channel_id"),
        Index("ix_recommendations_target_channel", "target_channel_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    source_analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"),
        nullable=True,
    )
    search_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("search_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Сценарий 6: откуда строился embedding-профиль и какой канал предложили
    seed_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
    )

    recommendation_type: Mapped[str] = mapped_column(String(96), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    body: Mapped[str | None] = mapped_column(Text(), nullable=True)

    payload_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=6), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    source_analysis: Mapped[Analysis | None] = relationship(
        "Analysis",
        back_populates="recommendations",
        foreign_keys=[source_analysis_id],
    )
    search_run: Mapped[SearchRun | None] = relationship(
        "SearchRun",
        back_populates="recommendations",
        foreign_keys=[search_run_id],
    )
    seed_channel: Mapped[Channel | None] = relationship(
        "Channel",
        back_populates="recommendations_seeded_here",
        foreign_keys=[seed_channel_id],
    )
    target_channel: Mapped[Channel | None] = relationship(
        "Channel",
        back_populates="recommendations_as_similar_target",
        foreign_keys=[target_channel_id],
    )
