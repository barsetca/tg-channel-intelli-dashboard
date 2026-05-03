"""Маппинг ORM → ``PostMetricRow`` / ``ChannelMetricContext`` без логики расчётов."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from app.models.channel import Channel
from app.models.post import Post
from app.services.channel_metrics.types import ChannelMetricContext, PostMetricRow


def post_row_from_orm(post: Post) -> PostMetricRow:
    at = post.posted_at
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return PostMetricRow(
        posted_at=at,
        views=post.views_count,
        forwards=post.forwards_count,
    )


def posts_rows_from_orm(posts: Iterable[Post]) -> list[PostMetricRow]:
    return [post_row_from_orm(p) for p in posts]


def channel_context_from_orm(
    channel: Channel,
    *,
    now_utc: datetime | None = None,
) -> ChannelMetricContext:
    return ChannelMetricContext(
        subscriber_count=channel.subscriber_count,
        now_utc=now_utc,
    )
