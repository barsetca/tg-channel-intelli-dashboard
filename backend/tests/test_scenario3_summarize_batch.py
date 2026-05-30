"""Сценарий 3: батчевое резюме постов вместо N последовательных LLM."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.intelligence_service import IntelligenceService, PostForAnalysis


def test_post_summary_from_llm_dict_fills_search_text_fallback() -> None:
    post = PostForAnalysis(
        message_id=1,
        published_at=datetime.now(timezone.utc),
        clean_text="Текст поста про путешествия",
        urls=[],
        hashtags=[],
        mentions=[],
        post_type="text",
        has_media=False,
        media_type=None,
        is_forwarded=False,
        is_reply=False,
        language="ru",
    )
    out = IntelligenceService._post_summary_from_llm_dict({"post_summary_short": "Кратко"}, post)
    assert out["post_summary_short"] == "Кратко"
    assert out["post_search_text"] == "Текст поста про путешествия"
