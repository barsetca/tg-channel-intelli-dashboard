"""Смешение naive / aware UTC в датах постов не должно ломать контекст (сценарий 2)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.ai.schemas.context import PostSnippet
from app.ai.stages.context_builder import ChannelPipelineInput, build_context_bundle


def test_build_context_bundle_sorts_mixed_tz_posts() -> None:
    naive = datetime(2025, 6, 1, 15, 0, 0)
    aware = datetime(2025, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
    inp = ChannelPipelineInput(
        user_intent="test",
        channel_title=None,
        channel_username=None,
        posts=[
            PostSnippet(aware, "второй"),
            PostSnippet(naive, "первый"),
        ],
    )
    bundle = build_context_bundle(inp)
    assert bundle.post_count == 2
    assert "2025-06-01" in bundle.combined_posts_text
    assert "2025-06-03" in bundle.combined_posts_text
