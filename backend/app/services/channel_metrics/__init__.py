"""
Движок метрик канала: чистые функции по постам + адаптеры ORM.

Пример::

    from datetime import datetime, timezone
    from app.services.channel_metrics import compute_channel_metrics, PostMetricRow

    posts = [
        PostMetricRow(datetime(2025, 1, 1, tzinfo=timezone.utc), views=100, forwards=2),
        PostMetricRow(datetime(2025, 1, 3, tzinfo=timezone.utc), views=200, forwards=5),
    ]
    snap = compute_channel_metrics(posts, now_utc=datetime(2025, 1, 4, tzinfo=timezone.utc))
"""

from app.services.channel_metrics.adapters import (
    channel_context_from_orm,
    post_row_from_orm,
    posts_rows_from_orm,
)
from app.services.channel_metrics.compute import (
    compute_activity_score,
    compute_avg_views,
    compute_channel_metrics,
    compute_consistency_score,
    compute_engagement_proxy,
    compute_posting_frequency,
)
from app.services.channel_metrics.types import (
    ChannelMetricContext,
    ChannelMetricsSnapshot,
    MetricWeights,
    PostMetricRow,
)

__all__ = [
    "ChannelMetricContext",
    "ChannelMetricsSnapshot",
    "MetricWeights",
    "PostMetricRow",
    "compute_activity_score",
    "compute_avg_views",
    "compute_channel_metrics",
    "compute_consistency_score",
    "compute_engagement_proxy",
    "compute_posting_frequency",
    "channel_context_from_orm",
    "post_row_from_orm",
    "posts_rows_from_orm",
]
