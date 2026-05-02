"""ORM: сценарий 7 — выгрузка JSON/CSV, статус и путь к артефакту."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin


class ExportJob(Base, TimestampMixin):
    """Фоновая или синхронная задача экспорта с фильтром области и файлом результата."""

    __tablename__ = "export_jobs"
    __table_args__ = (Index("ix_export_jobs_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    export_format: Mapped[str] = mapped_column(String(16), nullable=False)  # json | csv | ...
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")

    # Какие сущности и диапазоны включить в выборку
    scope_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    artifact_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
