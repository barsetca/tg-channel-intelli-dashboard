"""Поиск актуальной информации в интернете через OpenAI Responses API."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.ai.orchestration.errors import PipelineOpenAIError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _extract_responses_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", None) or []:
            ctype = getattr(content, "type", None)
            if ctype in ("output_text", "text"):
                text = getattr(content, "text", None)
                if text:
                    parts.append(str(text))
    return "\n".join(parts).strip()


class PublishingWebResearch:
    """Один вызов Responses API с инструментом web_search_preview."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.openai_api_key:
            raise PipelineOpenAIError("OPENAI_API_KEY не задан.")
        self._client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        self._model = self._settings.openai_chat_model

    async def research_topic(
        self,
        *,
        topic: str,
        extra_info: str | None = None,
    ) -> str:
        topic_clean = topic.strip()
        if len(topic_clean) < 3:
            raise ValueError("Тема слишком короткая для веб-поиска.")

        user_input = (
            f"Тема поста для Telegram-канала: {topic_clean}\n"
            "Задача: найти в интернете самую свежую актуальную информацию на текущий момент "
            "(новости, цифры, даты, тренды, недавние события).\n"
            "Ответ на русском: структурированные факты с указанием дат/источников где возможно. "
            "Не придумывай данные — только то, что удалось найти в поиске."
        )
        if extra_info and extra_info.strip():
            user_input += f"\n\nДополнительный контекст от редактора:\n{extra_info.strip()}"

        try:
            response = await self._client.responses.create(
                model=self._model,
                tools=[{"type": "web_search_preview"}],
                input=user_input,
            )
        except Exception as exc:
            raise PipelineOpenAIError(
                f"Веб-поиск не удался (проверьте модель {self._model!r} и доступ к Responses API): {exc}"
            ) from exc

        text = _extract_responses_text(response)
        if not text:
            raise PipelineOpenAIError("Веб-поиск вернул пустой ответ.")
        logger.info("publishing web research ok topic_len=%s result_len=%s", len(topic_clean), len(text))
        return text
