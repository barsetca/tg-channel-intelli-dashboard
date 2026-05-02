"""ORM: точечные «снимки» состояния канала для трендов и ретроспектив."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.channel import Channel


class Snapshot(Base, TimestampMixin):
    """
    Снимок метрик/структурированного состояния на момент sampled_at.
    Примеры: число подписчиков, агрегаты по охватам, дайджест контента за день (JSON в metrics_json).
    """

    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshots_channel_sampled_at", "channel_id", "sampled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Тип снимка: subscribers, engagement_daily, ingest_checkpoint и т.п.
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    metrics_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)

    channel: Mapped[Channel] = relationship(back_populates="snapshots")
    analyses_about_snapshot: Mapped[list[Analysis]] = relationship(
        "Analysis",
        back_populates="snapshot_subject",
        foreign_keys="Analysis.snapshot_id",
        cascade="all, delete-orphan",
    )
