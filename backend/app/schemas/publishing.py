"""API-схемы модуля публикации в Telegram."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    image_size: str | None = Field(
        None,
        description="Размер изображения (переопределяет OPENAI_IMAGE_SIZE для этого запроса)",
    )
    image_quality: str | None = Field(
        None,
        description="Качество (переопределяет OPENAI_IMAGE_QUALITY для этого запроса)",
    )
    custom_image_description: str | None = Field(
        None,
        max_length=2000,
        description="Описание желаемого изображения; LLM сформирует промпт для Images API",
    )
    use_web_search: bool = Field(
        True,
        description="Искать актуальную информацию в интернете перед генерацией текста",
    )
    generate_image: bool = Field(
        True,
        description="Вызывать OpenAI Images; если false — только текст и промпт для картинки",
    )
    media_base64: str | None = Field(None, description="Медиафайл при публикации (base64)")
    media_filename: str | None = Field(None, max_length=255, description="Имя файла, напр. clip.mp4")


class PublishingImageOptionsResponse(BaseModel):
    model: str
    family: Literal["gpt-image", "dall-e-3", "dall-e-2"]
    sizes: list[str]
    qualities: list[str]
    default_size: str
    default_quality: str


class GeneratedPostResponse(BaseModel):
    topic: str
    target_char_count: int
    actual_char_count: int
    output_mode: str
    post_text: str | None = None
    image_prompt_used: str
    image_model: str | None = None
    image_base64: str | None = Field(None, description="PNG/JPEG в base64; null если generate_image=false")
    image_generated: bool = True


class PublishGeneratedRequest(GeneratePostRequest):
    channel_ref: str = Field(..., min_length=2, description="@username или ссылка t.me/...")


class PublishManualRequest(BaseModel):
    channel_ref: str = Field(..., min_length=2)
    text: str | None = Field(None, max_length=4096)
    image_base64: str | None = Field(None, description="Устар.: используйте media_*")
    media_base64: str | None = Field(None, description="Изображение, видео или аудио (base64)")
    media_filename: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _text_or_media(self) -> PublishManualRequest:
        has_media = bool(self.media_base64 or self.image_base64)
        has_text = bool((self.text or "").strip())
        if not has_media and not has_text:
            raise ValueError("Укажите текст и/или медиафайл.")
        return self


class SendChatMessageRequest(BaseModel):
    chat_ref: str = Field(..., min_length=2, description="@username, id чата или ссылка")
    text: str | None = Field(None, max_length=4096)
    media_base64: str | None = None
    media_filename: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def _text_or_media(self) -> SendChatMessageRequest:
        has_media = bool(self.media_base64)
        has_text = bool((self.text or "").strip())
        if not has_media and not has_text:
            raise ValueError("Укажите текст и/или медиафайл.")
        return self


class PublishResultResponse(BaseModel):
    telegram_message_id: int
    peer_ref: str
    published_at_utc: datetime
    had_image: bool
    had_text: bool
    had_media: bool = False


class PublishGeneratedResponse(BaseModel):
    generated: GeneratedPostResponse
    published: PublishResultResponse


class AuthorStylePreviewResponse(BaseModel):
    samples: str
    source_hint: str
