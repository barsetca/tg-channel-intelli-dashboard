"""
Чистые функции расчёта метрик Telegram-канала по постам.

Формулы (кратко):
-----------------
**avg_views** — среднее арифметическое ``views`` по постам, где ``views`` не ``None`` и > 0.
Если таких нет → ``None``.

**posting_frequency** — оценка постов в неделю по интервалу между первым и последним постом
в выборке: ``7 * (N - 1) / span_weeks``, ``span_weeks = max(Δt_weeks, min_span_weeks)``.
При ``N < 2`` интервал не определён → ``None``.

**engagement_proxy** — среднее по постам ``min(forwards / max(views,1), cap)``
(прокси «репосты к просмотрам»). ``forwards=None`` → 0.
Результат в ``[0, cap]``; при ``cap=1`` это по сути ``[0, 1]``.

**activity_score** в ``[0, 100]``: выпуклая комбинация
- частоты публикаций (относительно ``posting_frequency_ref_per_week``),
- свежести последнего поста (к ``now_utc``),
- объёма выборки (логарифм числа постов).

**consistency_score** в ``[0, 100]``: регулярность интервалов между соседними постами
(по возрастанию ``posted_at``): ``100 * exp(-CV / scale)``, где ``CV = std(gaps)/mean(gaps)``
по интервалам в часах; при <2 постах — нейтральное значение 50.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone
from statistics import mean, pstdev

from app.services.channel_metrics.types import (
    ChannelMetricContext,
    ChannelMetricsSnapshot,
    MetricWeights,
    PostMetricRow,
)

# --- Вспомогательные чистые функции -------------------------------------------------


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hours_between(a: datetime, b: datetime) -> float:
    return abs((b - a).total_seconds()) / 3600.0


def _sorted_posts(posts: Sequence[PostMetricRow]) -> list[PostMetricRow]:
    return sorted(posts, key=lambda p: _ensure_aware_utc(p.posted_at))


# --- Публичные расчёты (чистые) ----------------------------------------------------


def compute_avg_views(posts: Sequence[PostMetricRow]) -> float | None:
    vals = [p.views for p in posts if p.views is not None and p.views > 0]
    if not vals:
        return None
    return float(sum(vals)) / float(len(vals))


def compute_posting_frequency(
    posts: Sequence[PostMetricRow],
    *,
    weights: MetricWeights | None = None,
) -> float | None:
    """
    Постов в неделю по крайним датам выборки: ``7 * (N-1) / span_weeks``.
    При одном посте возвращает ``None`` (скорость интервала не определена).
    """
    w = weights or MetricWeights()
    seq = _sorted_posts(posts)
    n = len(seq)
    if n < 2:
        return None
    t0 = _ensure_aware_utc(seq[0].posted_at)
    t1 = _ensure_aware_utc(seq[-1].posted_at)
    span_weeks = max(_hours_between(t0, t1) / 168.0, w.min_span_weeks)
    return 7.0 * float(n - 1) / span_weeks


def compute_engagement_proxy(
    posts: Sequence[PostMetricRow],
    *,
    weights: MetricWeights | None = None,
) -> float:
    """
    Средняя доля репостов от просмотров (с капом на пост), ``[0, engagement_forward_rate_cap]``.
    """
    w = weights or MetricWeights()
    cap = w.engagement_forward_rate_cap
    ratios: list[float] = []
    for p in posts:
        v = p.views
        if v is None or v <= 0:
            continue
        f = 0 if p.forwards is None else max(int(p.forwards), 0)
        ratios.append(min(float(f) / float(v), cap))
    if not ratios:
        return 0.0
    return float(mean(ratios))


def compute_consistency_score(
    posts: Sequence[PostMetricRow],
    *,
    weights: MetricWeights | None = None,
) -> float:
    """
    Чем ровнее интервалы между постами, тем выше score.
    При 0–1 посте — нейтральные 50 (нет интервалов).
    """
    w = weights or MetricWeights()
    seq = _sorted_posts(posts)
    if len(seq) < 2:
        return 50.0
    gaps_h: list[float] = []
    for a, b in zip(seq[:-1], seq[1:], strict=True):
        ha = _ensure_aware_utc(a.posted_at)
        hb = _ensure_aware_utc(b.posted_at)
        gaps_h.append(_hours_between(ha, hb))
    if len(gaps_h) == 1:
        return 100.0
    m = mean(gaps_h)
    if m <= 0:
        return 50.0
    sd = pstdev(gaps_h)
    cv = sd / m
    return float(100.0 * math.exp(-cv / w.consistency_cv_scale))


def _recency_component(last_post_at: datetime, now_utc: datetime) -> float:
    """Компонента свежести в ``[0, 1]`` по последнему посту."""
    last = _ensure_aware_utc(last_post_at)
    now = _ensure_aware_utc(now_utc)
    hours = max(0.0, (now - last).total_seconds() / 3600.0)
    # кусочно-линейная: <72ч → 1, до 14 суток плавно к 0.25, дальше экспоненциальный хвост
    if hours <= 72.0:
        return 1.0
    if hours <= 14.0 * 24.0:
        span = 14.0 * 24.0 - 72.0
        t = (hours - 72.0) / span
        return 1.0 - 0.75 * t
    return float(max(0.05, math.exp(-(hours - 14.0 * 24.0) / (30.0 * 24.0))))


def _volume_component(n_posts: int, ref: float) -> float:
    if n_posts <= 0:
        return 0.0
    return float(math.log1p(n_posts) / math.log1p(ref))


def compute_activity_score(
    posts: Sequence[PostMetricRow],
    *,
    now_utc: datetime,
    weights: MetricWeights | None = None,
) -> float:
    """
    ``[0, 100]``: частота (если известна), свежесть последнего поста, логарифм объёма выборки.
    Если ``posting_frequency`` is ``None``, частотная часть берётся как 0.
    """
    w = weights or MetricWeights()
    seq = _sorted_posts(posts)
    n = len(seq)
    if n == 0:
        return 0.0

    freq = compute_posting_frequency(posts, weights=w)
    freq_norm = 0.0 if freq is None else min(freq / w.posting_frequency_ref_per_week, 1.0)

    last_at = _ensure_aware_utc(seq[-1].posted_at)
    rec = _recency_component(last_at, now_utc)

    vol = _volume_component(n, w.volume_ref_posts)

    raw = (
        w.activity_w_frequency * freq_norm
        + w.activity_w_recency * rec
        + w.activity_w_volume * vol
    )
    return float(max(0.0, min(100.0, 100.0 * raw)))


def compute_channel_metrics(
    posts: Sequence[PostMetricRow],
    *,
    context: ChannelMetricContext | None = None,
    weights: MetricWeights | None = None,
    now_utc: datetime | None = None,
) -> ChannelMetricsSnapshot:
    """
    Сводный расчёт всех метрик. ``now_utc`` для activity: из ``context`` или явный аргумент;
    если оба ``None`` — берётся UTC-«сейчас» через ``datetime.now(timezone.utc)`` (удобно в проде,
    в тестах передавайте явно).
    """
    w = weights or MetricWeights()
    ctx = context or ChannelMetricContext()
    resolved_now = now_utc or ctx.now_utc or datetime.now(timezone.utc)

    avg_v = compute_avg_views(posts)
    freq = compute_posting_frequency(posts, weights=w)
    eng = compute_engagement_proxy(posts, weights=w)
    act = compute_activity_score(posts, now_utc=resolved_now, weights=w)
    cons = compute_consistency_score(posts, weights=w)

    meta: dict[str, float | int | str | None] = {
        "now_utc_used": resolved_now.isoformat(),
        "subscriber_count": ctx.subscriber_count,
    }

    return ChannelMetricsSnapshot(
        avg_views=avg_v,
        posting_frequency=freq,
        engagement_proxy=eng,
        activity_score=act,
        consistency_score=cons,
        posts_used=len(posts),
        meta=meta,
    )
