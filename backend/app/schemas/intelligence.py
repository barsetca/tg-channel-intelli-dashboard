"""
Pydantic-схемы для сценариев intelligence API (поиск, анализ, семантика, экспорт).

Поля с `Field(description=...)` попадают в OpenAPI для фронтенда и контрактов.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from app.schemas.channel import ChannelRead

# --- Сценарий 1 + 8: поиск каналов ---


class SearchChannelsRequest(BaseModel):
    """Тело запроса «Найти каналы» (форма из user_scenario)."""

    topic: str = Field(..., min_length=1, description="Тематика / сфера (обязательна)")
    count: int | None = Field(20, ge=1, description="Сколько каналов вернуть")
    offset: int = Field(0, ge=0, description="Смещение для постраничной выдачи")
    min_subscribers: int | None = Field(None, ge=0, description="Мин. подписчиков")
    max_subscribers: int | None = Field(None, ge=0, description="Макс. подписчиков")
    channel_type: Literal["new_only", "all"] = Field("all", description="Только новые или все")
    live_channel_mode: Literal["new", "saved"] = Field(
        "new",
        description="Режим telegram_live: новые каналы или актуализация сохраненных",
    )
    language: str | None = Field(None, max_length=32, description="Язык (подсказка)")
    region_country: str | None = Field(None, max_length=128, description="Регион / страна")
    username_query: str | None = Field(
        None,
        max_length=255,
        description="Поиск по username канала",
    )
    selected_channel_ids: list[int] = Field(
        default_factory=list,
        description="Явно выбранные каналы каталога для актуализации в telegram_live",
        max_length=20,
    )
    last_post_from: date | None = Field(
        None,
        description="Дата последнего поста: от (saved_catalog)",
    )
    last_post_to: date | None = Field(
        None,
        description="Дата последнего поста: до (saved_catalog)",
    )
    extra_conditions: str | None = Field(
        None,
        max_length=2000,
        description="Доп. условия свободным текстом",
    )
    search_source: Literal["saved_catalog", "telegram_live"] = Field(
        "saved_catalog",
        description=(
            "Где искать: локальный каталог (SQLite) или живой Telegram "
            "(Telethon, фоновая задача)"
        ),
    )
    sort_by: Literal["subscriber_count", "last_sync_at"] = Field(
        "subscriber_count",
        description="Сортировка для saved_catalog",
    )
    sort_order: Literal["asc", "desc"] = Field(
        "desc",
        description="Направление сортировки для saved_catalog",
    )

    @model_validator(mode="after")
    def subscriber_range_consistent(self) -> Self:
        if (
            self.min_subscribers is not None
            and self.max_subscribers is not None
            and self.max_subscribers < self.min_subscribers
        ):
            raise ValueError("max_subscribers не может быть меньше min_subscribers")
        if self.search_source == "telegram_live":
            if self.min_subscribers is not None or self.max_subscribers is not None:
                raise ValueError("Для telegram_live фильтр по подписчикам отключён")
            if self.last_post_from is not None or self.last_post_to is not None:
                raise ValueError("Для telegram_live фильтр по дате поста отключён")
            if self.count is None:
                raise ValueError("Для telegram_live укажите count (1..15)")
            if self.count < 1 or self.count > 15:
                raise ValueError("Для telegram_live count должен быть в диапазоне 1..15")
            if len(self.selected_channel_ids) > 20:
                raise ValueError("Можно выбрать не более 20 сохранённых каналов")
            if any(int(x) <= 0 for x in self.selected_channel_ids):
                raise ValueError("selected_channel_ids должны содержать только положительные id")
        if (
            self.last_post_from is not None
            and self.last_post_to is not None
            and self.last_post_to < self.last_post_from
        ):
            raise ValueError("last_post_to не может быть раньше last_post_from")
        return self


class ManualReviewFlags(BaseModel):
    """Сценарий 8: запрос слишком общий — без автоматического поиска по каталогу."""

    needs_review: bool = Field(..., description="Требуется уточнение запроса пользователем")
    reason: str = Field(..., description="Короткая причина")
    hints: list[str] = Field(default_factory=list, description="Рекомендации по уточнению")


class AIPlanAndCollectRequest(BaseModel):
    """Адаптер ТЗ: вход для POST /ai/plan_and_collect."""

    query: str = Field(..., min_length=1, max_length=2000, description="Запрос пользователя")


class AIPlanAndCollectResponse(BaseModel):
    """Адаптер ТЗ: строгий JSON-ответ planning шага."""

    plan_steps: list[str] = Field(default_factory=list, min_length=1, max_length=5)
    api_url: str
    fields_to_keep: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    needs_review: bool = False


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
    last_sync_at: datetime | None = Field(None, description="Дата записи/обновления канала")
    primary_topic: str | None = Field(None, description="Тематика")
    topic_search: str | None = Field(None, description="Исходный поисковый topic из Telegram формы")
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
    has_more: bool = Field(
        False,
        description="Есть ли следующая страница результатов для saved_catalog",
    )


class SearchTopicOptionsResponse(BaseModel):
    """Справочник тем/ниш для выпадайки saved_catalog."""

    items: list[str] = Field(default_factory=list)


class DataShowcaseItem(BaseModel):
    """Строка витрины данных (нормализованный snapshot из внешнего источника)."""

    audit_run_id: int
    item_id: int
    created_at: datetime | None = None
    source: str | None = None
    record_json: dict[str, Any] | list[Any] | None = None


class DataShowcaseResponse(BaseModel):
    """Ответ витрины данных."""

    limit: int
    items: list[DataShowcaseItem] = Field(default_factory=list)


class ManualReviewJournalItem(BaseModel):
    """Элемент журнала ручной проверки."""

    source: Literal["audit", "search", "analyze", "semantic"]
    reference_id: int
    created_at: datetime | None = None
    reason: str
    status: str | None = None
    details: dict[str, Any] | list[Any] | None = None


class ManualReviewJournalResponse(BaseModel):
    """Ответ журнала ручной проверки."""

    limit: int
    source_filter: Literal["all", "audit", "search", "analyze", "semantic"] = "all"
    items: list[ManualReviewJournalItem] = Field(default_factory=list)


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
    post_limit: int = Field(
        10,
        ge=3,
        le=20,
        description="Сколько последних постов подтянуть из Telegram при пустой локальной истории",
    )


class AnalyzeChannelByHandleRequest(BaseModel):
    """Сценарий 2: запуск анализа по ссылке или username."""

    channel_ref: str = Field(
        ...,
        min_length=2,
        max_length=512,
        description="Ссылка на канал (t.me/...) или username (@name)",
    )
    user_intent: str = Field(
        "Проанализируй канал: тематика, стиль, риски и рекомендации для рекламодателя.",
        max_length=4000,
        description="Пользовательская формулировка задачи для LLM",
    )
    post_limit: int = Field(
        10,
        ge=3,
        le=20,
        description="Сколько последних постов подтянуть из Telegram перед анализом",
    )


class ContentStrategyReport(BaseModel):
    """Выводы по позиционированию и контент-стратегии (для UI отчёта)."""

    goals: str = ""
    main_topics: str = ""
    formats: str = ""
    cadence: str = ""
    rubricator: str = ""
    target_audience: str = ""
    seo_focus: str = ""
    engagement: str = ""


class ToneOfVoiceReport(BaseModel):
    """Тональность и стиль (для UI отчёта)."""

    style: str = ""
    lexicon: str = ""
    emotions: str = ""
    distance: str = ""
    consistency: str = ""
    vs_positioning: str = ""


class ChannelAnalysisReport(BaseModel):
    """Пользовательский отчёт сценария 2 (агрегат из БД + pipeline result)."""

    channel_description: str
    topic: str
    subscribers_count: int | None = None
    channel_url: str | None = Field(None, description="Публичная ссылка t.me на канал")
    channel_created_display: str | None = Field(
        None,
        description="Дата создания канала в Telegram, DD.MM.YYYY",
    )
    channel_age_display: str | None = Field(
        None,
        description="Возраст канала от даты создания до сегодня",
    )
    posts_last_30_days: int | None = Field(
        None,
        description="Постов за последние 30 дней (по тексту канала; короткие посты учитываются, служебный мусор отфильтрован)",
    )
    total_posts_filtered: int | None = Field(
        None,
        description="Всего постов с непустым текстом в объединённой выборке (Telegram recent+history и БД), без порога 30 симв.",
    )
    report_created_at: datetime | None = None
    publication_frequency: str
    avg_post_length: int | None
    posts_summary: str = Field(
        "",
        description="Краткое содержание проанализированных постов (из стадии summarization)",
    )
    content_strategy: ContentStrategyReport = Field(default_factory=ContentStrategyReport)
    tone_of_voice: ToneOfVoiceReport = Field(default_factory=ToneOfVoiceReport)
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ChannelAnalysisHistoryItem(BaseModel):
    """Строка списка сохранённых анализов."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int | None
    channel_display_ref: str | None = None
    status: str
    analyzer_id: str
    created_at: datetime


class SavedChannelAnalysisDetail(BaseModel):
    """Деталь сохранённого отчёта для повторного просмотра."""

    analysis_id: int
    channel_id: int
    status: str
    message: str
    created_at: datetime
    report: ChannelAnalysisReport | None = None
    channel_display_ref: str | None = Field(
        None,
        description="Метка канала для UI: @username, ссылка или запасной идентификатор",
    )


class AnalyzeChannelResponse(BaseModel):
    """Идентификатор записи анализа и краткий статус."""

    analysis_id: int
    channel_id: int
    status: str = Field(..., description="completed | blocked_validation | failed")
    message: str = Field(..., description="Человекочитаемый итог")
    manual_review: ManualReviewFlags | None = None
    report: ChannelAnalysisReport | None = None
    channel_display_ref: str | None = Field(
        None,
        description="Метка канала для UI: @username, ссылка или запасной идентификатор",
    )


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

    post_limit: int = Field(10, ge=3, le=20, description="Число последних постов")


class SummarizePostsByHandleRequest(BaseModel):
    """Сценарий 3: запуск сводки по ссылке или username канала."""

    channel_ref: str = Field(
        ...,
        min_length=2,
        max_length=512,
        description="Ссылка на канал (t.me/...) или username (@name)",
    )
    post_limit: int = Field(10, ge=3, le=20, description="Число последних постов")


class SummarizePostsResponse(BaseModel):
    """Краткая сводка по постам."""

    channel_id: int
    channel_display_ref: str | None = None
    posts_used: int
    summary: str = Field(..., description="Ключевые темы и идеи по окну последних постов (LLM)")
    per_post_summaries: list[str] = Field(default_factory=list, description="Краткие сводки по каждому посту")
    stored_analysis_hint: str | None = Field(
        None,
        description="Подсказка: summary можно писать в Analysis и векторный индекс",
    )


# --- Сценарий 4: семантический поиск ---


class SemanticSearchRequest(BaseModel):
    """Семантический запрос сценария 4 по накопленным post/window данным."""

    query: str = Field(..., min_length=2, max_length=2000, description="Вопрос в свободной форме")
    limit: int = Field(12, ge=1, le=30, description="Сколько итоговых результатов показать")
    channel_username: str | None = Field(
        None,
        description="Ограничить поиск одним каналом по username (без @)",
    )


class SemanticSearchHit(BaseModel):
    """Один документ из векторного поиска."""

    point_id: str
    score: float | None = Field(None, description="Релевантность (Qdrant score)")
    channel_id: int | None = None
    channel_username: str | None = None
    post_id: int | None = None
    published_at: datetime | None = None
    source_url: str | None = None
    content_type: str | None = None
    text_preview: str | None = Field(None, description="Начало текста чанка")


class SemanticSource(BaseModel):
    channel_username: str | None = None
    message_id: int | None = None
    source_url: str | None = None
    score: float | None = None
    summary: str | None = None


class SemanticResultItem(BaseModel):
    channel_username: str | None = None
    title: str | None = None
    relevance_reason: str | None = None
    source_url: str | None = None
    score: float | None = None


class SemanticSearchResponse(BaseModel):
    """Сценарий 4: unified JSON-ответ с обязательным `needs_review`."""

    needs_review: bool = False
    reason: str | None = None
    query: str
    mode: Literal["post_search", "channel_search", "question_answering_over_posts"] | None = None
    answer: str | None = None
    results: list[SemanticResultItem] = Field(default_factory=list)
    sources: list[SemanticSource] = Field(default_factory=list)
    hits: list[SemanticSearchHit] = Field(default_factory=list)
    synthesis_placeholder: str | None = None
    gate_matched_topics: list[str] | None = Field(
        None,
        description="Темы из LLM-gate, сопоставленные с каталогом; используются для пост-фильтрации выдачи.",
    )


# --- Сценарий 6: похожие каналы ---


class SimilarChannelSignals(BaseModel):
    topic_overlap: float = Field(ge=0.0, le=1.0)
    style_similarity: float = Field(ge=0.0, le=1.0)
    frequency_similarity: float = Field(ge=0.0, le=1.0)


class SimilarChannelItem(BaseModel):
    channel_id: int
    channel_username: str | None = None
    title: str | None = None
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    supporting_topics: list[str] = Field(default_factory=list)
    supporting_signals: SimilarChannelSignals
    missing_data: list[str] = Field(
        default_factory=list,
        description="Чего не хватает по этому каналу для «полного» семантического матча",
    )


class SimilarSourceChannel(BaseModel):
    channel_id: int
    channel_username: str | None = None


class SimilarChannelsResponse(BaseModel):
    needs_review: bool = False
    reason: str | None = None
    mode: Literal["similar_channels"] | None = None
    source_channel: SimilarSourceChannel | None = None
    results: list[SimilarChannelItem] = Field(default_factory=list)
    quality_notes: list[str] = Field(
        default_factory=list,
        description="Пояснения о качестве подборки (деградация, неполные данные)",
    )


# --- Сценарий 5: сравнение ---


class CompareChannelsRequest(BaseModel):
    """2–3 канала для сравнительной таблицы."""

    channel_ids: list[int] = Field(..., min_length=2, max_length=3)

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


class CompareChannelMetrics(BaseModel):
    """Расчётные метрики по сопоставимому окну (30 дней)."""

    posts_in_window: int
    posting_frequency_per_week: float
    avg_views: float
    median_views: float
    p75_views: float
    avg_forwards: float
    er_forward_rate_mean: float
    er_forward_rate_p75: float
    weekly_stability_score: float = Field(ge=0.0, le=100.0)
    views_trend_slope: float
    tone_label: str
    topic_labels: list[str] = Field(default_factory=list)
    commercial_intent_share: float = Field(ge=0.0, le=1.0)
    normalized_score: float = Field(ge=0.0, le=100.0)


class CompareChannelInsight(BaseModel):
    channel_id: int
    username: str | None = None
    strengths: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    metrics: CompareChannelMetrics


class CompareChannelsResponse(BaseModel):
    """Сценарий 5: полноценное сравнительное досье по окну 30 дней."""

    rows: list[CompareChannelRow]
    comparison_notes: str | None = Field(
        None,
        description="Краткие выводы (MVP: шаблон; можно заменить на LLM)",
    )
    comparison_window_days: int = 30
    generated_at: datetime | None = None
    insights: list[CompareChannelInsight] = Field(default_factory=list)


# --- Сценарий 7: экспорт (формат задаётся query-параметром `format=json|csv`) ---
