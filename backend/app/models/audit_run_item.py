"""ORM: строки результатов аудита — привязка к каналу (и опционально к посту) с рангом и снимком данных."""

from __future__ import annotations

from decimal import Decimal
from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin


class AuditRunItem(Base, TimestampMixin):
    """
    Гранулярная запись («records» из сценария 1): одна строка набора результатов —
    название/subscribers частоту и пр. сохраняем в snapshot_json даже если канал потом изменится.
    """

    __tablename__ = "audit_run_items"
    __table_args__ = (
        Index("ix_audit_run_items_audit_rank", "audit_run_id", "display_order"),
        Index("ix_audit_run_items_channel", "channel_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    audit_run_id: Mapped[int] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Семантический тип строки для фронта: channel_candidate | ...
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="channel")

    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=6), nullable=True)

    # Карточка канала на момент выдачи: тематика, ссылка, частота постов...
    snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    telegram_username_fallback: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    audit_run: Mapped["AuditRun"] = relationship("AuditRun", back_populates="items")
    channel: Mapped["Channel | None"] = relationship("Channel", back_populates="audit_run_items")
