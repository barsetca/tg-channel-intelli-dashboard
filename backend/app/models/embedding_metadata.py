"""ORM: связь поста ↔ вектор в Qdrant (сам вектор — только во внешнем хранилище)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.post import Post


class EmbeddingMetadata(Base, TimestampMixin):
    """
    Метаданные эмбеддинга: модель, размерность, идентификатор точки в Qdrant.
    Один пост может быть разбит на несколько chunk_index (например длинное сообщение).
    """

    __tablename__ = "embeddings_metadata"
    __table_args__ = (
        UniqueConstraint(
            "embedding_model",
            "qdrant_collection",
            "qdrant_point_id",
            name="uq_emb_model_collection_point",
        ),
        UniqueConstraint(
            "post_id",
            "embedding_model",
            "chunk_index",
            name="uq_emb_post_model_chunk",
        ),
        Index("ix_embeddings_metadata_post_id", "post_id"),
        Index("ix_embeddings_metadata_collection", "qdrant_collection"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    dims: Mapped[int] = mapped_column(Integer, nullable=False)

    qdrant_collection: Mapped[str] = mapped_column(String(256), nullable=False)
    qdrant_point_id: Mapped[str] = mapped_column(String(128), nullable=False)

    extras_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    post: Mapped[Post] = relationship(back_populates="embeddings")
