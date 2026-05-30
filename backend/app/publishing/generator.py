"""Генерация текста и изображений поста через OpenAI."""

from __future__ import annotations

import logging
from typing import Literal

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionDeveloperMessageParam, ChatCompletionUserMessageParam

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.orchestration.errors import PipelineConfigurationError, PipelineOpenAIError
from app.ai.prompts.registry import prompt_renderer
from app.core.config import Settings, get_settings
from app.publishing.schemas import GeneratedPostContent, PostDraftLLM
from app.publishing.image_api import resolve_openai_image_generate_kwargs
from app.publishing.style import load_author_style_samples

logger = logging.getLogger(__name__)

OutputMode = Literal["post_with_image", "infographic_only"]


class PostContentGenerator:
    """Chat (structured) + Images API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openai_api_key:
            raise PipelineConfigurationError("OPENAI_API_KEY не задан — генерация постов недоступна.")
        self._chat = OpenAIStageClient(self._settings)
        self._images = AsyncOpenAI(api_key=self._settings.openai_api_key)

    async def generate_draft(
        self,
        *,
        topic: str,
        target_char_count: int,
        extra_info: str | None = None,
    ) -> PostDraftLLM:
        topic_clean = topic.strip()
        if len(topic_clean) < 3:
            raise ValueError("Тема поста слишком короткая (минимум 3 символа).")
        target = max(200, min(4096, int(target_char_count)))
        style = load_author_style_samples()
        prompt = prompt_renderer().render(
            "publishing/post_draft.j2",
            author_style_samples=style,
            topic=topic_clean,
            target_char_count=target,
            extra_info=(extra_info or "").strip() or None,
        )
        messages = [
            ChatCompletionDeveloperMessageParam(
                role="developer",
                content="Ты создаёшь контент для Telegram. Соблюдай схему ответа.",
            ),
            ChatCompletionUserMessageParam(role="user", content=prompt),
        ]
        draft = await self._chat.parse_structured(messages=messages, response_format=PostDraftLLM)
        post_text = draft.post_text.strip()
        if not post_text:
            raise PipelineOpenAIError("Модель вернула пустой текст поста.")
        return draft

    async def generate_image_bytes(self, *, prompt_en: str) -> tuple[bytes, str]:
        prompt = prompt_en.strip()
        if len(prompt) < 10:
            raise ValueError("Промпт для изображения слишком короткий.")
        model = self._settings.openai_image_model
        img_kwargs = resolve_openai_image_generate_kwargs(self._settings)
        try:
            resp = await self._images.images.generate(
                prompt=prompt[:4000],
                n=1,
                **img_kwargs,
            )
        except Exception as exc:
            raise PipelineOpenAIError(f"Генерация изображения не удалась: {exc}") from exc
        item = resp.data[0] if resp.data else None
        if item is None:
            raise PipelineOpenAIError("OpenAI Images вернул пустой результат.")
        if item.b64_json:
            import base64

            return base64.b64decode(item.b64_json), str(img_kwargs.get("model", model))
        if item.url:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(item.url)
                r.raise_for_status()
                return r.content, str(img_kwargs.get("model", model))
        raise PipelineOpenAIError("Нет url/b64_json в ответе OpenAI Images.")

    async def build_content(
        self,
        *,
        topic: str,
        target_char_count: int,
        extra_info: str | None,
        output_mode: OutputMode,
    ) -> tuple[GeneratedPostContent, bytes]:
        draft = await self.generate_draft(
            topic=topic,
            target_char_count=target_char_count,
            extra_info=extra_info,
        )
        post_text = draft.post_text.strip()
        if output_mode == "infographic_only":
            image_prompt = draft.infographic_prompt_en.strip()
            publish_text: str | None = None
        else:
            image_prompt = draft.illustration_prompt_en.strip()
            publish_text = post_text
        image_bytes, model = await self.generate_image_bytes(prompt_en=image_prompt)
        meta = GeneratedPostContent(
            topic=topic.strip(),
            target_char_count=target_char_count,
            actual_char_count=len(post_text),
            output_mode=output_mode,
            post_text=post_text,
            publish_text=publish_text,
            image_prompt_used=image_prompt,
            image_model=model,
        )
        return meta, image_bytes
