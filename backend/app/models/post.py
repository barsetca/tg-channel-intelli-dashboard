"""ORM: сообщения канала — основа текстовых и векторных сценариев."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.channel import Channel
    from app.models.embedding_metadata import EmbeddingMetadata


class Post(Base, TimestampMixin):
    """
    Пост (сообщение) в канале.
    Индекс (channel_id, telegram_message_id) уникален — идемпотентная синхронизация.
    """

    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("channel_id", "telegram_message_id", name="uq_posts_channel_tg_msg"),
        Index("ix_posts_channel_posted_at", "channel_id", "posted_at"),
        Index("ix_posts_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    telegram_message_id: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_media: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Статистикa Telegram (если доступна в сообщении канала — сценарий 2)
    views_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forwards_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Урезанный объект Telethon/MTProto или нормализованный контент для отладки
    raw_payload_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    channel: Mapped[Channel] = relationship(back_populates="posts")

    embeddings: Mapped[list[EmbeddingMetadata]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )
    analyses_about_post: Mapped[list[Analysis]] = relationship(
        "Analysis",
        back_populates="post_subject",
        foreign_keys="Analysis.post_id",
        cascade="all, delete-orphan",
    )
