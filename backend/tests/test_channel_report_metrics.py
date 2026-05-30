from datetime import datetime, timedelta, timezone

import pytest

from app.services.channel_report_metrics import (
    channel_age_days,
    compute_publication_frequency_per_week,
    count_relevant_posts,
    format_channel_age,
    format_date_ru,
    infer_channel_start_at,
    infer_metric_channel_start_at,
    is_metric_post_text,
    is_relevant_post_text,
    resolve_channel_created_at,
)
from app.services.intelligence_service import _MetricPostRow


def test_infer_channel_start_at_from_oldest_post() -> None:
    posts = [
        _MetricPostRow(datetime(2025, 11, 1, tzinfo=timezone.utc), "b" * 40),
        _MetricPostRow(datetime(2025, 10, 5, tzinfo=timezone.utc), "a" * 40),
        _MetricPostRow(datetime(2026, 1, 1, tzinfo=timezone.utc), "c" * 40),
    ]
    start = infer_channel_start_at(posts)
    assert start is not None
    assert format_date_ru(start) == "05.10.2025"


def test_publication_frequency_four_posts_over_seven_months() -> None:
    created = datetime(2025, 10, 5, tzinfo=timezone.utc)
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(created + timedelta(days=i * 50), f"post number {i} " * 5)
        for i in range(4)
    ]
    total = count_relevant_posts(posts)
    assert total == 4
    freq = compute_publication_frequency_per_week(
        total,
        channel_created_at=created,
        sample_posts=posts,
        now=now,
    )
    assert freq is not None
    age_days = channel_age_days(created, now=now)
    assert age_days is not None
    expected = 4.0 / (age_days / 7.0)
    assert freq == pytest.approx(expected, rel=0.01)
    assert freq < 0.2


def test_publication_frequency_short_span_not_inflated() -> None:
    base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(base + timedelta(hours=i), f"content line {i} " * 5)
        for i in range(10)
    ]
    freq = compute_publication_frequency_per_week(
        count_relevant_posts(posts),
        channel_created_at=None,
        sample_posts=posts,
        now=base + timedelta(hours=12),
    )
    assert freq is not None
    assert freq < 50.0


def test_format_channel_age_russian() -> None:
    created = datetime(2024, 10, 5, tzinfo=timezone.utc)
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    age = format_channel_age(created, now=now)
    assert age is not None
    assert "год" in age or "лет" in age
    assert "месяц" in age or "месяцев" in age


def test_is_relevant_filters_short_and_ads() -> None:
    assert not is_relevant_post_text("short")
    assert not is_relevant_post_text("x" * 20)
    assert is_relevant_post_text("x" * 40)
    assert not is_relevant_post_text("x" * 40 + " реклама " + "y" * 10)


def test_metric_counter_includes_short_posts() -> None:
    assert not is_metric_post_text("")
    assert not is_metric_post_text("   ")
    assert is_metric_post_text("ab")
    assert is_metric_post_text("hello")
    base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(base, "v1.2 out"),
        _MetricPostRow(base + timedelta(days=1), "x" * 40),
        _MetricPostRow(base + timedelta(days=2), "no"),
        _MetricPostRow(base + timedelta(days=3), "Short ann"),
    ]
    assert count_relevant_posts(posts) == 4


def test_metric_counter_keeps_bot_and_robot_mentions() -> None:
    """Подстрока «бот» не должна отсекать посты (в отличие от старой эвристики)."""
    assert is_metric_post_text("Новый чат-бот на GPT-4 для разработчиков")
    assert is_metric_post_text("Обзор роботов и автоматизации в dev")
    posts = [
        _MetricPostRow(datetime(2026, 4, 1, tzinfo=timezone.utc), "чат-бот"),
        _MetricPostRow(datetime(2026, 4, 2, tzinfo=timezone.utc), "робот"),
        _MetricPostRow(datetime(2026, 4, 3, tzinfo=timezone.utc), "обычный пост"),
    ]
    assert count_relevant_posts(posts) == 3


def test_resolve_channel_created_at_takes_earliest_date() -> None:
    entity = datetime(2020, 1, 28, 13, 16, 47, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(datetime(2026, 5, 17, tzinfo=timezone.utc), "пост"),
        _MetricPostRow(datetime(2026, 5, 20, tzinfo=timezone.utc), "ещё"),
    ]
    assert resolve_channel_created_at(telegram_channel_date=entity, posts=posts) == entity


def test_resolve_channel_created_at_prefers_older_post_over_recent_entity_date() -> None:
    entity = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(datetime(2022, 6, 15, tzinfo=timezone.utc), "старый пост"),
        _MetricPostRow(datetime(2026, 5, 20, tzinfo=timezone.utc), "новый"),
    ]
    assert resolve_channel_created_at(telegram_channel_date=entity, posts=posts) == datetime(
        2022, 6, 15, tzinfo=timezone.utc
    )


def test_count_relevant_posts_since_creation_date() -> None:
    created = datetime(2026, 5, 10, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(datetime(2026, 5, 1, tzinfo=timezone.utc), "до создания"),
        _MetricPostRow(datetime(2026, 5, 15, tzinfo=timezone.utc), "после"),
        _MetricPostRow(datetime(2026, 5, 20, tzinfo=timezone.utc), "ещё"),
    ]
    assert count_relevant_posts(posts) == 3
    assert count_relevant_posts(posts, since=created) == 2


def test_infer_metric_channel_start_ignores_empty_old_rows() -> None:
    old = datetime(2018, 1, 1, tzinfo=timezone.utc)
    recent = datetime(2026, 4, 20, tzinfo=timezone.utc)
    posts = [
        _MetricPostRow(old, None),
        _MetricPostRow(old, "   "),
        _MetricPostRow(recent, "первый содержательный пост " * 3),
    ]
    assert infer_channel_start_at(posts) == old
    assert infer_metric_channel_start_at(posts) == recent
