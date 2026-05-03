"""Типы данных для движка метрик: независимы от ORM, удобны для юнит-тестов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PostMetricRow:
    """
    Минимальный срез поста для расчёта метрик.
    ``posted_at`` должен быть с таймзоной (UTC предпочтительно).
    """

    posted_at: datetime
    views: int | None = None
    forwards: int | None = None


@dataclass(frozen=True)
class ChannelMetricContext:
    """Контекст канала (опционально): подписчики и «текущий момент» для recency."""

    subscriber_count: int | None = None
    now_utc: datetime | None = None


@dataclass(frozen=True)
class MetricWeights:
    """
    Коэффициенты для расширения / тюнинга без смены сигнатур чистых функций.
    Значения по умолчанию согласованы с формулами в ``compute.py``.
    """

    # posting_frequency: (N-1) интервалов / span_weeks; span не меньше этого (недель)
    min_span_weeks: float = 1e-6
    # activity_score: при какой частоте (постов/нед) нормализованная частота = 1.0
    posting_frequency_ref_per_week: float = 14.0
    # activity_score: веса компонент [frequency, recency, volume]
    activity_w_frequency: float = 0.55
    activity_w_recency: float = 0.35
    activity_w_volume: float = 0.10
    # activity: объём — log-стиснуть к 1 при n >= volume_ref_posts
    volume_ref_posts: float = 100.0
    # consistency: масштаб CV в экспоненте (больше → мягче штраф за неравномерность)
    consistency_cv_scale: float = 2.0
    # engagement: верхняя капа на отношение forwards/views на пост
    engagement_forward_rate_cap: float = 1.0

    def __post_init__(self) -> None:
        s = self.activity_w_frequency + self.activity_w_recency + self.activity_w_volume
        if abs(s - 1.0) > 1e-6:
            raise ValueError("Сумма activity_w_* должна быть 1.0")


@dataclass(frozen=True)
class ChannelMetricsSnapshot:
    """Итоговый снимок метрик канала (все поля явно заданы, без ORM)."""

    avg_views: float | None
    posting_frequency: float | None
    engagement_proxy: float
    activity_score: float
    consistency_score: float
    posts_used: int = 0
    meta: dict[str, float | int | str | None] = field(default_factory=dict)
