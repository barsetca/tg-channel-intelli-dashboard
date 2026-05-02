"""ORM: результат AI-/эвристического пайплайна над каналом, постом или снимком."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.post import Post
    from app.models.snapshot import Snapshot


class Analysis(Base, TimestampMixin):
    """
    Ровно один «субъект» анализа: channel XOR post XOR snapshot.
    Поля статусов и JSON результата — под сценарии суммаризации, классификации, качества данных.
    """

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN channel_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN post_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN snapshot_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_analyses_single_subject",
        ),
        Index("ix_analyses_status_created", "status", "created_at"),
        Index("ix_analyses_analyzer", "analyzer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=True,
    )
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("snapshots.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Ключ пайплайна: channel_summary_v1, toxicity_gate, embed_refresh и т.д.
    analyzer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")

    input_refs_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)

    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    channel_subject: Mapped[Channel | None] = relationship(
        back_populates="analyses_about_channel",
        foreign_keys=[channel_id],
    )
    post_subject: Mapped[Post | None] = relationship(
        back_populates="analyses_about_post",
        foreign_keys=[post_id],
    )
    snapshot_subject: Mapped[Snapshot | None] = relationship(
        back_populates="analyses_about_snapshot",
        foreign_keys=[snapshot_id],
    )

    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="source_analysis",
        foreign_keys="[Recommendation.source_analysis_id]",
        passive_deletes=True,
    )
