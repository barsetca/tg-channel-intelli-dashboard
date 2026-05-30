from __future__ import annotations

import pytest

from app.schemas.intelligence import ChannelAnalysisReport, ContentStrategyReport, ToneOfVoiceReport
from app.services.channel_analysis_pdf import (
    _resolve_font_path,
    build_channel_analysis_pdf,
    channel_analysis_pdf_filename,
    channel_analysis_report_slug,
)


def test_channel_analysis_pdf_filename_format() -> None:
    assert channel_analysis_report_slug(channel_display_ref="@dev_to_ai", channel_id=1, analysis_id=10) == "dev_to_ai_10"
    assert channel_analysis_pdf_filename(channel_display_ref="@dev_to_ai", channel_id=1, analysis_id=10) == "dev_to_ai_10.pdf"


def test_build_channel_analysis_pdf_bytes() -> None:
    try:
        _resolve_font_path()
    except FileNotFoundError:
        pytest.skip("DejaVuSans.ttf not installed")

    report = ChannelAnalysisReport(
        channel_description="Описание тестового канала о путешествиях.",
        topic="Путешествия",
        subscribers_count=1200,
        channel_url="https://t.me/example",
        channel_created_display="05.10.2025",
        channel_age_display="7 месяцев 10 дней",
        posts_last_30_days=1,
        total_posts_filtered=4,
        publication_frequency="0.13 поста/нед",
        avg_post_length=420,
        posts_summary="Краткая сводка по постам канала.",
        content_strategy=ContentStrategyReport(goals="Рост аудитории"),
        tone_of_voice=ToneOfVoiceReport(style="Дружелюбный"),
        strengths=["Сильная визуальная подача"],
        risks=["Низкая частота публикаций"],
        recommendations=["Увеличить регулярность постов"],
    )
    data = build_channel_analysis_pdf(
        report=report,
        channel_label="@example",
        channel_id=7,
        analysis_id=42,
        status="completed",
        message="Анализ завершён",
    )
    assert isinstance(data, bytes)
    assert data[:4] == b"%PDF"
