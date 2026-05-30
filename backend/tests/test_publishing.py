"""Тесты модуля публикации (без OpenAI/Telethon)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.publishing.image_api import resolve_openai_image_generate_kwargs
from app.publishing.schemas import PostDraftLLM
from app.publishing.style import load_author_style_samples, resolve_style_samples_path


def test_author_style_samples_load() -> None:
    text = load_author_style_samples()
    assert "нейросет" in text.lower() or "ИИ" in text
    path = resolve_style_samples_path()
    assert path.is_file()


def test_post_draft_schema() -> None:
    draft = PostDraftLLM(
        post_text="Тестовый пост 🎯",
        illustration_prompt_en="modern editorial illustration, no text",
        infographic_prompt_en="vertical infographic, icons, no long text",
    )
    assert len(draft.post_text) > 5


def test_bundled_style_file_exists() -> None:
    bundled = Path(__file__).resolve().parents[1] / "app" / "publishing" / "data" / "author_style_samples.txt"
    assert bundled.is_file()


def test_gpt_image_quality_medium_accepted_in_settings() -> None:
    s = Settings(
        openai_image_model="gpt-image-1-mini",
        openai_image_quality="medium",
        openai_image_size="1024x1792",
    )
    kw = resolve_openai_image_generate_kwargs(s)
    assert kw["quality"] == "medium"
    assert kw["size"] == "1024x1536"


def test_dalle3_maps_medium_to_standard() -> None:
    s = Settings(openai_image_model="dall-e-3", openai_image_quality="medium")
    kw = resolve_openai_image_generate_kwargs(s)
    assert kw["quality"] == "standard"
