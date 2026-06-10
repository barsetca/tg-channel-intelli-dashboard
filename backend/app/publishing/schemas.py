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
        description=(
            "Промпт на английском для инфографики. Если нужны подписи — перечисли их "
            "в кавычках кириллицей (Russian text): «…». Не переводи подписи на английский."
        ),
    )


class ImagePromptFromHintLLM(BaseModel):
    """Structured output: промпт для Images API по описанию редактора."""

    post_content: str = Field(description="Краткое содержание поста (контекст для визуала)")
    image_generation_prompt: str = Field(
        description="Промпт для OpenAI Images: сцена и стиль (обычно на английском)",
    )
    labels_on_image_ru: list[str] = Field(
        default_factory=list,
        description="Точные русские надписи (кириллица) для отображения на изображении",
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

