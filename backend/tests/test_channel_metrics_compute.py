"""Юнит-тесты чистого движка метрик канала."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.channel_metrics.compute import (
    compute_activity_score,
    compute_avg_views,
    compute_channel_metrics,
    compute_consistency_score,
    compute_engagement_proxy,
    compute_posting_frequency,
)
from app.services.channel_metrics.types import MetricWeights, PostMetricRow

UTC = timezone.utc


def dt(day: int, hour: int = 12) -> datetime:
    return datetime(2025, 1, day, hour, tzinfo=UTC)


def test_avg_views_empty_and_values() -> None:
    assert compute_avg_views([]) is None
    assert compute_avg_views([PostMetricRow(dt(1), views=None)]) is None
    assert compute_avg_views([PostMetricRow(dt(1), views=0)]) is None
    two = [
        PostMetricRow(dt(1), views=10),
        PostMetricRow(dt(2), views=30),
    ]
    assert compute_avg_views(two) == 20.0


def test_posting_frequency_requires_two_posts() -> None:
    assert compute_posting_frequency([PostMetricRow(dt(1))]) is None
    # ровно 7 дней между двумя постами → 1 интервал за 1 неделю → 7 * 1 / 1 = 7 постов/нед
    posts = [PostMetricRow(dt(1)), PostMetricRow(dt(8))]
    assert compute_posting_frequency(posts) == pytest.approx(7.0)


def test_posting_frequency_same_day_burst() -> None:
    posts = [PostMetricRow(dt(1, 10)), PostMetricRow(dt(1, 11))]
    f = compute_posting_frequency(posts)
    # span_weeks мал → высокая экстраполированная частота (посты в один день)
    assert f is not None and f > 7.0 * 24


def test_engagement_proxy() -> None:
    posts = [
        PostMetricRow(dt(1), views=100, forwards=10),
        PostMetricRow(dt(2), views=50, forwards=50),
    ]
    # (0.1 + min(1,1)) / 2 = 0.55
    assert compute_engagement_proxy(posts) == pytest.approx(0.55)


def test_consistency_perfect_intervals() -> None:
    posts = [PostMetricRow(dt(i), views=1) for i in range(1, 6)]  # каждые 24ч
    assert compute_consistency_score(posts) == pytest.approx(100.0)


def test_consistency_irregular() -> None:
    posts = [
        PostMetricRow(dt(1), views=1),
        PostMetricRow(dt(2), views=1),
        PostMetricRow(dt(10), views=1),
    ]
    s = compute_consistency_score(posts)
    assert 0.0 < s < 100.0


def test_consistency_single_post_neutral() -> None:
    assert compute_consistency_score([PostMetricRow(dt(1))]) == 50.0


def test_activity_score_zero_posts() -> None:
    assert compute_activity_score([], now_utc=dt(10)) == 0.0


def test_activity_score_composite() -> None:
    posts = [PostMetricRow(dt(i), views=100, forwards=1) for i in range(1, 8)]
    score = compute_activity_score(posts, now_utc=dt(7, 23))
    assert 0.0 < score <= 100.0


def test_compute_channel_metrics_snapshot() -> None:
    posts = [
        PostMetricRow(dt(1), views=100, forwards=5),
        PostMetricRow(dt(3), views=200, forwards=0),
    ]
    snap = compute_channel_metrics(posts, now_utc=dt(4))
    assert snap.posts_used == 2
    assert snap.avg_views == pytest.approx(150.0)
    assert snap.posting_frequency is not None
    assert 0.0 <= snap.engagement_proxy <= 1.0
    assert 0.0 <= snap.activity_score <= 100.0
    assert 0.0 <= snap.consistency_score <= 100.0
    assert "now_utc_used" in snap.meta


def test_metric_weights_invalid_sum_raises() -> None:
    with pytest.raises(ValueError):
        MetricWeights(activity_w_frequency=1.0, activity_w_recency=1.0, activity_w_volume=0.0)
