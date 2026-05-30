"""API-схемы модуля публикации в Telegram."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PublishableChannelResponse(BaseModel):
    telegram_channel_id: int
    username: str | None = None
    title: str | None = None


class GeneratePostRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="Тема поста")
    char_count: int = Field(1200, ge=200, le=4096, description="Целевое число символов")
    extra_info: str | None = Field(None, max_length=4000, description="Доп. контекст для LLM")
    output_mode: Literal["post_with_image", "infographic_only"] = Field(
        "post_with_image",
        description="post_with_image — картинка + текст; infographic_only — только инфографика",
    )


class GeneratedPostResponse(BaseModel):
    topic: str
    target_char_count: int
    actual_char_count: int
    output_mode: str
    post_text: str | None = None
    image_prompt_used: str
    image_model: str
    image_base64: str = Field(description="PNG/JPEG в base64 для предпросмотра")


class PublishGeneratedRequest(GeneratePostRequest):
    channel_ref: str = Field(..., min_length=2, description="@username или ссылка t.me/...")


class PublishManualRequest(BaseModel):
    channel_ref: str = Field(..., min_length=2)
    text: str | None = Field(None, max_length=4096)
    image_base64: str | None = Field(None, description="Опциональное изображение (base64)")


class SendChatMessageRequest(BaseModel):
    chat_ref: str = Field(..., min_length=2, description="@username, id чата или ссылка")
    text: str = Field(..., min_length=1, max_length=4096)


class PublishResultResponse(BaseModel):
    telegram_message_id: int
    peer_ref: str
    published_at_utc: datetime
    had_image: bool
    had_text: bool


class PublishGeneratedResponse(BaseModel):
    generated: GeneratedPostResponse
    published: PublishResultResponse


class AuthorStylePreviewResponse(BaseModel):
    samples: str
    source_hint: str
