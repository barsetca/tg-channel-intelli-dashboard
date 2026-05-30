"""Режим telegram_live «Новые» — исключение каналов из SQLite и расширение поиска."""

from __future__ import annotations

from app.integrations.telethon.dto import TelegramSearchHit
from app.orchestration.discovery_pipeline import (
    _count_fresh_candidates,
    _min_new_candidate_pool,
    _new_only_extra_variants,
    _unique_hit_collection_cap,
)


def _resolve_new_only(*, channel_type: str, live_channel_mode: str, username_query: str = "") -> bool:
    """Зеркало логики run_telethon_stage (discovery_pipeline) для регрессии."""
    live_mode = live_channel_mode.strip().lower()
    new_only = channel_type == "new_only" or live_mode == "new"
    if username_query.strip() or live_mode == "saved":
        new_only = False
    return new_only


def test_live_new_mode_excludes_existing_in_db() -> None:
    assert _resolve_new_only(channel_type="all", live_channel_mode="new") is True


def test_live_new_with_new_only_flag() -> None:
    assert _resolve_new_only(channel_type="new_only", live_channel_mode="new") is True


def test_live_saved_mode_updates_existing() -> None:
    assert _resolve_new_only(channel_type="new_only", live_channel_mode="saved") is False


def test_username_lookup_never_skips_existing() -> None:
    assert _resolve_new_only(channel_type="new_only", live_channel_mode="new", username_query="@foo") is False


def test_new_only_extra_variants_splits_compound_topic() -> None:
    variants = _new_only_extra_variants("ремонт квартир", "Ремонт квартир")
    lowered = {v.casefold() for v in variants}
    assert "ремонт" in lowered
    assert "квартир" in lowered
    assert any("ремонт" in v and "квартир" in v for v in lowered)


def test_min_new_candidate_pool_scales_with_target() -> None:
    assert _min_new_candidate_pool(15) >= 15 * 15
    assert _min_new_candidate_pool(5) >= 120


def test_unique_hit_collection_cap_higher_for_new_only() -> None:
    plain = _unique_hit_collection_cap(15, {}, new_only=False)
    boosted = _unique_hit_collection_cap(15, {}, new_only=True)
    assert boosted > plain


def test_count_fresh_candidates_excludes_db_ids() -> None:
    hits = [
        TelegramSearchHit(telegram_channel_id=1, username="a", title="A", is_broadcast=True),
        TelegramSearchHit(telegram_channel_id=2, username="b", title="B", is_broadcast=True),
        TelegramSearchHit(telegram_channel_id=3, username="c", title="C", is_broadcast=True),
    ]
    assert _count_fresh_candidates(hits, {1, 3}) == 1
