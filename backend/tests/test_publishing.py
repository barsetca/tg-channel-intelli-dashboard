"""Тесты модуля публикации (без OpenAI/Telethon)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.publishing.image_api import get_publishing_image_options, resolve_openai_image_generate_kwargs
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


def test_image_options_gpt_image_mini() -> None:
    s = Settings(openai_image_model="gpt-image-1-mini", openai_image_size="1024x1024", openai_image_quality="medium")
    opts = get_publishing_image_options(s)
    assert opts.family == "gpt-image"
    assert "1024x1024" in opts.sizes
    assert "medium" in opts.qualities
    assert opts.default_quality == "medium"


def test_image_kwargs_request_override() -> None:
    s = Settings(openai_image_model="gpt-image-1-mini", openai_image_size="1024x1024", openai_image_quality="low")
    kw = resolve_openai_image_generate_kwargs(s, size_override="1536x1024", quality_override="high")
    assert kw["size"] == "1536x1024"
    assert kw["quality"] == "high"


def test_image_prompt_from_hint_schema() -> None:
    from app.publishing.generator import _finalize_image_prompt_from_hint
    from app.publishing.schemas import ImagePromptFromHintLLM

    row = ImagePromptFromHintLLM(
        post_content="Суть поста",
        image_generation_prompt="modern infographic, friendly robot host, neon cyberpunk style",
        labels_on_image_ru=["Создай Reels", "Нейросети", "Шаг 1"],
    )
    final = _finalize_image_prompt_from_hint(row)
    assert "«Создай Reels»" in final
    assert "Cyrillic" in final
    assert "not translated to English" in final
