"""Pydantic-схемы модуля публикации (внутренние + structured output OpenAI)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PostDraftLLM(BaseModel):
    """Structured output: один вызов chat — текст и промпты для визуала."""

    post_text: str = Field(description="Готовый текст поста для Telegram с эмодзи")
    illustration_prompt_en: str = Field(
        description="Краткий промпт на английском для иллюстрации к посту (без текста на картинке)",
    )
    infographic_prompt_en: str = Field(
        description="Промпт на английском для инфографики, передающей суть поста без дублирования текста",
    )


class GeneratedPostContent(BaseModel):
    topic: str
    target_char_count: int
    actual_char_count: int
    output_mode: Literal["post_with_image", "infographic_only"]
    post_text: str
    publish_text: str | None = None
    image_prompt_used: str
    image_model: str

