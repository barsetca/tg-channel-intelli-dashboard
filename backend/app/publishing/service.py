"""Оркестрация: генерация контента и публикация через Telethon."""

from __future__ import annotations

import logging
from typing import Literal

from app.integrations.telethon.dto import PublishableChannelBrief, TelegramPublishResult
from app.integrations.telethon.user_session_service import TelethonUserSessionService
from app.publishing.generator import PostContentGenerator
from app.publishing.schemas import GeneratedPostContent
from app.publishing.style import load_author_style_samples

logger = logging.getLogger(__name__)

OutputMode = Literal["post_with_image", "infographic_only"]


class PublishingService:
    def __init__(
        self,
        *,
        telegram: TelethonUserSessionService,
        generator: PostContentGenerator | None = None,
    ) -> None:
        self._telegram = telegram
        self._generator = generator

    def _gen(self) -> PostContentGenerator:
        if self._generator is None:
            self._generator = PostContentGenerator()
        return self._generator

    async def list_publishable_channels(self) -> list[PublishableChannelBrief]:
        return await self._telegram.list_publishable_channels()

    def author_style_preview(self, *, max_chars: int = 2000) -> str:
        text = load_author_style_samples()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3] + "..."

    async def generate_preview(
        self,
        *,
        topic: str,
        target_char_count: int,
        extra_info: str | None,
        output_mode: OutputMode,
    ) -> tuple[GeneratedPostContent, bytes]:
        return await self._gen().build_content(
            topic=topic,
            target_char_count=target_char_count,
            extra_info=extra_info,
            output_mode=output_mode,
        )

    async def publish_to_channel(
        self,
        *,
        channel_ref: str,
        text: str | None,
        image_bytes: bytes | None,
    ) -> TelegramPublishResult:
        return await self._telegram.publish_to_channel(
            channel_ref,
            text=text,
            image_bytes=image_bytes,
        )

    async def send_chat_message(self, *, chat_ref: str, text: str) -> TelegramPublishResult:
        return await self._telegram.send_user_message(chat_ref, text=text)

    async def generate_and_publish(
        self,
        *,
        channel_ref: str,
        topic: str,
        target_char_count: int,
        extra_info: str | None,
        output_mode: OutputMode,
    ) -> tuple[GeneratedPostContent, bytes, TelegramPublishResult]:
        meta, image_bytes = await self.generate_preview(
            topic=topic,
            target_char_count=target_char_count,
            extra_info=extra_info,
            output_mode=output_mode,
        )
        pub = await self.publish_to_channel(
            channel_ref=channel_ref,
            text=meta.publish_text,
            image_bytes=image_bytes,
        )
        logger.info(
            "publishing done channel_ref=%r mode=%s message_id=%s",
            channel_ref,
            output_mode,
            pub.telegram_message_id,
        )
        return meta, image_bytes, pub
