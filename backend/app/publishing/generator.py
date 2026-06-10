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
from app.publishing.image_api import resolve_openai_image_generate_kwargs
from app.publishing.schemas import GeneratedPostContent, ImagePromptFromHintLLM, PostDraftLLM
from app.publishing.style import load_author_style_samples
from app.publishing.web_research import PublishingWebResearch

logger = logging.getLogger(__name__)

OutputMode = Literal["post_with_image", "infographic_only"]


def _finalize_image_prompt_from_hint(result: ImagePromptFromHintLLM) -> str:
    """Собирает финальный промпт для Images API с явным указанием кириллических надписей."""
    prompt = result.image_generation_prompt.strip()
    labels = [label.strip() for label in result.labels_on_image_ru if label.strip()]
    if labels:
        quoted = ", ".join(f"«{label}»" for label in labels)
        prompt += (
            "\n\nIMPORTANT — render these exact Russian (Cyrillic) text labels on the image, "
            "legible, not translated to English: "
            f"{quoted}. Use neon glow typography if the scene style allows."
        )
    return prompt


class PostContentGenerator:
    """Chat (structured) + Images API; опционально веб-поиск."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openai_api_key:
            raise PipelineConfigurationError("OPENAI_API_KEY не задан — генерация постов недоступна.")
        self._chat = OpenAIStageClient(self._settings)
        self._images = AsyncOpenAI(api_key=self._settings.openai_api_key)

    async def _fetch_web_research(self, *, topic: str, extra_info: str | None) -> str:
        researcher = PublishingWebResearch(self._settings)
        return await researcher.research_topic(topic=topic, extra_info=extra_info)

    async def generate_draft(
        self,
        *,
        topic: str,
        target_char_count: int,
        extra_info: str | None = None,
        web_research_context: str | None = None,
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
            web_research_context=(web_research_context or "").strip() or None,
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

    async def generate_image_prompt_from_hint(
        self,
        *,
        topic: str,
        post_text: str,
        image_description: str,
        output_mode: OutputMode,
    ) -> str:
        desc = image_description.strip()
        if len(desc) < 5:
            raise ValueError("Описание изображения слишком короткое.")
        prompt = prompt_renderer().render(
            "publishing/image_prompt_from_hint.j2",
            topic=topic.strip(),
            post_text=post_text.strip(),
            image_description=desc,
            output_mode=output_mode,
        )
        messages = [
            ChatCompletionDeveloperMessageParam(
                role="developer",
                content=(
                    "Верни JSON: post_content, image_generation_prompt, labels_on_image_ru. "
                    "Если редактор просит русские надписи — заполни labels_on_image_ru кириллицей, не переводи."
                ),
            ),
            ChatCompletionUserMessageParam(role="user", content=prompt),
        ]
        result = await self._chat.parse_structured(
            messages=messages,
            response_format=ImagePromptFromHintLLM,
        )
        image_prompt = _finalize_image_prompt_from_hint(result)
        if len(image_prompt) < 10:
            raise PipelineOpenAIError("Модель вернула слишком короткий промпт для изображения.")
        return image_prompt

    async def generate_image_bytes(
        self,
        *,
        prompt_en: str,
        image_size: str | None = None,
        image_quality: str | None = None,
    ) -> tuple[bytes, str]:
        prompt = prompt_en.strip()
        if len(prompt) < 10:
            raise ValueError("Промпт для изображения слишком короткий.")
        img_kwargs = resolve_openai_image_generate_kwargs(
            self._settings,
            size_override=image_size,
            quality_override=image_quality,
        )
        model = str(img_kwargs.get("model", self._settings.openai_image_model))
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

            return base64.b64decode(item.b64_json), model
        if item.url:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.get(item.url)
                r.raise_for_status()
                return r.content, model
        raise PipelineOpenAIError("Нет url/b64_json в ответе OpenAI Images.")

    def _default_image_prompt(self, draft: PostDraftLLM, output_mode: OutputMode) -> str:
        if output_mode == "infographic_only":
            return draft.infographic_prompt_en.strip()
        return draft.illustration_prompt_en.strip()

    async def build_content(
        self,
        *,
        topic: str,
        target_char_count: int,
        extra_info: str | None,
        output_mode: OutputMode,
        use_web_search: bool = True,
        custom_image_description: str | None = None,
        image_size: str | None = None,
        image_quality: str | None = None,
        generate_image: bool = True,
    ) -> tuple[GeneratedPostContent, bytes | None]:
        web_context: str | None = None
        if use_web_search:
            web_context = await self._fetch_web_research(topic=topic, extra_info=extra_info)

        draft = await self.generate_draft(
            topic=topic,
            target_char_count=target_char_count,
            extra_info=extra_info,
            web_research_context=web_context,
        )
        post_text = draft.post_text.strip()

        custom_desc = (custom_image_description or "").strip()
        if custom_desc:
            image_prompt = await self.generate_image_prompt_from_hint(
                topic=topic,
                post_text=post_text,
                image_description=custom_desc,
                output_mode=output_mode,
            )
        else:
            image_prompt = self._default_image_prompt(draft, output_mode)

        if output_mode == "infographic_only":
            publish_text: str | None = None
        else:
            publish_text = post_text

        image_bytes: bytes | None = None
        image_model: str | None = None
        if generate_image:
            image_bytes, image_model = await self.generate_image_bytes(
                prompt_en=image_prompt,
                image_size=image_size,
                image_quality=image_quality,
            )
        else:
            image_model = self._settings.openai_image_model

        meta = GeneratedPostContent(
            topic=topic.strip(),
            target_char_count=target_char_count,
            actual_char_count=len(post_text),
            output_mode=output_mode,
            post_text=post_text,
            publish_text=publish_text,
            image_prompt_used=image_prompt,
            image_model=image_model or "",
        )
        return meta, image_bytes
