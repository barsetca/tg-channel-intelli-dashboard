"""ORM: универсальный аудит оркестрации (сценарии 1, 8, частично 5 — многошаговые действия пользователя)."""

from __future__ import annotations

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin


class AuditRun(Base, TimestampMixin):
    """
    Соответствует в спецификации блоку «audit_runs»: один запуск цепочки (поиск каналов,
    сравнение, и т.д.). Сценарий 8 (manual review) — в quality_gate_json.
    Конкретные «карточки» результатов см. AuditRunItem (аналог granular «records»).
    """

    __tablename__ = "audit_runs"
    __table_args__ = (
        Index("ix_audit_runs_kind_created", "audit_kind", "created_at"),
        Index("ix_audit_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # channel_discovery | channel_comparison | similar_channels | под будущие сценарии
    audit_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    # Исходные поля формы / запрос пользователя (тематика, диапазоны и т.д.)
    raw_user_input_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # Выход AI Planner (структурированный запрос после LLM шага)
    planner_output_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # Сценарий 8: {"needs_review": true, "reason": "..."}
    quality_gate_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # Итог операции целиком: сводное сравнение каналов, агрегаты поиска и т.п.
    result_summary_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    error_text: Mapped[str | None] = mapped_column(Text(), nullable=True)

    items: Mapped[list["AuditRunItem"]] = relationship(
        "AuditRunItem",
        back_populates="audit_run",
        cascade="all, delete-orphan",
    )
