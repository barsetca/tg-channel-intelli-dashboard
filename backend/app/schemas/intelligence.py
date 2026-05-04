"""
Pydantic-схемы для сценариев intelligence API (поиск, анализ, семантика, экспорт).

Поля с `Field(description=...)` попадают в OpenAPI для фронтенда и контрактов.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from app.schemas.channel import ChannelRead

# --- Сценарий 1 + 8: поиск каналов ---


class SearchChannelsRequest(BaseModel):
    """Тело запроса «Найти каналы» (форма из user_scenario)."""

    topic: str = Field(..., min_length=1, description="Тематика / сфера (обязательна)")
    count: int = Field(20, ge=1, le=100, description="Сколько каналов вернуть")
    min_subscribers: int | None = Field(None, ge=0, description="Мин. подписчиков")
    max_subscribers: int | None = Field(None, ge=0, description="Макс. подписчиков")
    channel_type: Literal["new_only", "all"] = Field("all", description="Только новые или все")
    language: str | None = Field(None, max_length=32, description="Язык (подсказка)")
    region_country: str | None = Field(None, max_length=128, description="Регион / страна")
    extra_conditions: str | None = Field(
        None,
        max_length=2000,
        description="Доп. условия свободным текстом",
    )
    search_source: Literal["saved_catalog", "telegram_live"] = Field(
        "saved_catalog",
        description="Где искать: локальный каталог (SQLite) или живой Telegram (Telethon, фоновая задача)",
    )

    @model_validator(mode="after")
    def subscriber_range_consistent(self) -> Self:
        if (
            self.min_subscribers is not None
            and self.max_subscribers is not None
            and self.max_subscribers < self.min_subscribers
        ):
            raise ValueError("max_subscribers не может быть меньше min_subscribers")
        return self


class ManualReviewFlags(BaseModel):
    """Сценарий 8: запрос слишком общий — без автоматического поиска по каталогу."""

    needs_review: bool = Field(..., description="Требуется уточнение запроса пользователем")
    reason: str = Field(..., description="Короткая причина")
    hints: list[str] = Field(default_factory=list, description="Рекомендации по уточнению")


class BackgroundSearchJob(BaseModel):
    """Фоновый поиск в Telegram; каналы появятся в каталоге после ingest."""

    job_id: str = Field(..., description="Идентификатор задания в OrchestrationCoordinator")
    kind: Literal["telegram_channel_discovery"] = "telegram_channel_discovery"
    status: Literal["queued", "running", "completed", "failed"] = Field(
        "queued",
        description="Состояние pipeline на момент ответа HTTP",
    )
    detail: str = Field("", description="Пояснение для UI / отладки")


class ChannelCard(BaseModel):
    """Карточка канала для таблицы результатов (сценарий 1)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    title: str | None
    description: str | None
    subscriber_count: int | None = Field(None, description="Подписчики")
    posts_per_week_estimate: float | None = Field(None, description="Оценка постов/нед")
    last_post_at: datetime | None = Field(None, description="Последний пост")
    primary_topic: str | None = Field(None, description="Тематика")
    invite_slug: str | None = Field(None, description="Ссылка / slug")
    language_hint: str | None = None
    region_country: str | None = None


class SearchChannelsResponse(BaseModel):
    """Ответ поиска: либо список карточек, либо manual review."""

    channels: list[ChannelCard] = Field(default_factory=list)
    manual_review: ManualReviewFlags | None = Field(
        None,
        description="Если задано — список может быть пустым",
    )
    normalized_filters: dict[str, object] = Field(
        default_factory=dict,
        description="Нормализованные фильтры (для аудита / UI)",
    )
    background_job: BackgroundSearchJob | None = Field(
        None,
        description="При search_source=telegram_live — фоновое задание Telethon→SQLite→…",
    )


# --- Сценарий 2: детализация и анализ ---


class ChannelDetail(ChannelRead):
    """Расширенная карточка канала для GET /channel/{id}."""

    model_config = ConfigDict(from_attributes=True)

    invite_slug: str | None = None
    subscriber_count: int | None = None
    last_post_at: datetime | None = None
    posts_per_week_estimate: float | None = None
    primary_topic: str | None = None
    language_hint: str | None = None
    region_country: str | None = None
    is_public_accessible: bool | None = None
    sync_status: str | None = None
    last_sync_at: datetime | None = None


class AnalyzeChannelRequest(BaseModel):
    """Опции запуска анализа (сценарий 2)."""

    user_intent: str = Field(
        "Проанализируй канал: тематика, стиль, риски и рекомендации для рекламодателя.",
        max_length=4000,
        description="Пользовательская формулировка задачи для LLM",
    )


class AnalyzeChannelResponse(BaseModel):
    """Идентификатор записи анализа и краткий статус."""

    analysis_id: int
    channel_id: int
    status: str = Field(..., description="completed | blocked_validation | failed")
    message: str = Field(..., description="Человекочитаемый итог")


class AnalysisRead(BaseModel):
    """Сырой результат анализа из БД (для последующего GET по analysis_id при расширении API)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int | None
    analyzer_id: str
    status: str
    result_json: dict[str, Any] | list[Any] | None = None
    error_detail: str | None = None


# --- Сценарий 3: сводка постов ---


class SummarizePostsRequest(BaseModel):
    """Сценарий 3: сколько последних постов свернуть в summary."""

    post_limit: int = Field(10, ge=1, le=100, description="Число последних постов")


class SummarizePostsResponse(BaseModel):
    """Краткая сводка по постам."""

    channel_id: int
    posts_used: int
    summary: str = Field(..., description="Ключевые темы и идеи (LLM)")
    stored_analysis_hint: str | None = Field(
        None,
        description="Подсказка: summary можно писать в Analysis и векторный индекс",
    )


# --- Сценарий 4: семантический поиск ---


class SemanticSearchRequest(BaseModel):
    """Семантический вопрос по корпусу (Qdrant + payload)."""

    query: str = Field(..., min_length=2, max_length=2000)
    limit: int = Field(15, ge=1, le=50)
    content_type: Literal["post", "summary", "profile"] | None = Field(
        None,
        description="Ограничить тип документа в индексе",
    )
    channel_id: int | None = Field(
        None,
        description="Ограничить поиск одним каналом (FK в payload)",
    )


class SemanticSearchHit(BaseModel):
    """Один документ из векторного поиска."""

    point_id: str
    score: float | None = Field(None, description="Релевантность (Qdrant score)")
    channel_id: int | None = None
    post_id: int | None = None
    content_type: str | None = None
    text_preview: str | None = Field(None, description="Начало текста чанка")


class SemanticSearchResponse(BaseModel):
    """Сценарий 4: top-k + место под LLM synthesis (пока без второго LLM-вызова в MVP)."""

    query: str
    hits: list[SemanticSearchHit]
    synthesis_placeholder: str | None = Field(
        None,
        description="Зарезервировано под ответ LLM по сниппетам (RAG synthesis)",
    )


# --- Сценарий 6: похожие каналы ---


class SimilarChannelItem(BaseModel):
    """Канал-кандидат с оценкой близости."""

    channel_id: int
    score: float | None = Field(None, description="Агрегированная близость по чанкам")
    title: str | None = None
    username: str | None = None


class SimilarChannelsResponse(BaseModel):
    """Список похожих каналов (агрегация по post hits из Qdrant)."""

    seed_channel_id: int
    similar: list[SimilarChannelItem]


# --- Сценарий 5: сравнение ---


class CompareChannelsRequest(BaseModel):
    """2–5 каналов для сравнительной таблицы."""

    channel_ids: list[int] = Field(..., min_length=2, max_length=5)

    @model_validator(mode="after")
    def unique_channel_ids(self) -> Self:
        if len(set(self.channel_ids)) != len(self.channel_ids):
            raise ValueError("channel_ids должны быть уникальными")
        return self


class CompareChannelRow(BaseModel):
    """Строка сравнения по одному каналу."""

    channel_id: int
    title: str | None
    username: str | None
    subscriber_count: int | None
    posts_per_week_estimate: float | None
    primary_topic: str | None


class CompareChannelsResponse(BaseModel):
    """Сценарий 5: метрики рядом; narrative — опционально через LLM позже."""

    rows: list[CompareChannelRow]
    comparison_notes: str | None = Field(
        None,
        description="Краткие выводы (MVP: шаблон; можно заменить на LLM)",
    )


# --- Сценарий 7: экспорт (формат задаётся query-параметром `format=json|csv`) ---
