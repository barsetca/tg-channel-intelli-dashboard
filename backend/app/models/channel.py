"""ORM: Telegram-каналы, привязка к учётке и сценариям синхронизации."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.audit_run_item import AuditRunItem
    from app.models.post import Post
    from app.models.recommendation import Recommendation
    from app.models.snapshot import Snapshot


class Channel(Base, TimestampMixin):
    """
    Метаданные канала (из Telethon/API).
    Карточка сценария 1 и отчёт сценария 2 дополняются вычислимыми/денормализованными полями.
    """

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger(), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)

    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Публичная ссылка @username или t.me — для карточки и экспорта
    invite_slug: Mapped[str | None] = mapped_column(String(512), nullable=True)

    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    subscriber_count: Mapped[int | None] = mapped_column(nullable=True)

    # Доступен ли канал анонимно (сценарий 2, шаг проверки)
    is_public_accessible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Денормализация последнего поста — для таблицы «найти каналы» без JOIN на каждый список
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Дата создания канала в Telegram (поле date сущности Channel в MTProto)
    telegram_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Оценочная частота публикаций (постов в неделю), заполняет воркер по истории постов / снимкам
    posts_per_week_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Тематика / теги (сценарий 1 карточка + анализ)
    primary_topic: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    # Исходная строка из формы Telegram live-поиска (для приоритетного поиска в saved catalog).
    topic_search: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    topics_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    # Контакты канала если известны (бот, email в описании не парсится автоматически — JSON вручную/пайплайн)
    contact_info_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    language_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region_country: Mapped[str | None] = mapped_column(String(128), nullable=True)

    extras_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    posts: Mapped[list[Post]] = relationship(back_populates="channel", cascade="all, delete-orphan")
    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    analyses_about_channel: Mapped[list[Analysis]] = relationship(
        "Analysis",
        back_populates="channel_subject",
        foreign_keys="Analysis.channel_id",
        cascade="all, delete-orphan",
    )

    audit_run_items: Mapped[list["AuditRunItem"]] = relationship(
        "AuditRunItem",
        back_populates="channel",
        foreign_keys="[AuditRunItem.channel_id]",
    )

    recommendations_seeded_here: Mapped[list["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="seed_channel",
        foreign_keys="Recommendation.seed_channel_id",
    )

    recommendations_as_similar_target: Mapped[list["Recommendation"]] = relationship(
        "Recommendation",
        back_populates="target_channel",
        foreign_keys="Recommendation.target_channel_id",
    )
