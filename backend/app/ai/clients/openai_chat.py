"""
Асинхронный клиент вызовов OpenAI для стадий pipeline.
Транспортные ошибки (429, 5xx, таймаут): **tenacity**.
Repair JSON — отдельный путь без цикла ретраев.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.orchestration.errors import PipelineConfigurationError, PipelineOpenAIError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


def _is_retryable_openai_error(exc: BaseException) -> bool:
    """Решение о повторе: сеть, rate limit, серверные 5xx."""
    if isinstance(exc, (APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500 or exc.status_code == 429
    return False


class OpenAIStageClient:
    """Обёртка AsyncOpenAI: `parse` (Pydantic) и текстовые вызовы (summary / repair)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        key = self._settings.openai_api_key
        if not key:
            raise PipelineConfigurationError("OPENAI_API_KEY не задан — AI pipeline недоступен.")
        self._client = AsyncOpenAI(api_key=key)
        self._model = self._settings.openai_chat_model

    @property
    def model(self) -> str:
        return self._model

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception(_is_retryable_openai_error),
        before_sleep=lambda rs: logger.warning(
            "OpenAI retry: attempt=%s error=%s", rs.attempt_number, rs.outcome.exception()
        ),
    )
    async def parse_structured(
        self,
        *,
        messages: Sequence[ChatCompletionMessageParam],
        response_format: type[TModel],
    ) -> TModel:
        """
        Structured output → Pydantic: используем `chat.completions.parse` из официального SDK.
        """
        try:
            resp = await self._client.chat.completions.parse(
                model=self._model,
                messages=list(messages),
                response_format=response_format,  # type: ignore[arg-type]
            )
        except Exception as exc:
            raise PipelineOpenAIError(f"OpenAI parse вызов не удался: {exc}") from exc

        parsed = resp.choices[0].message.parsed
        if parsed is None:
            raise PipelineOpenAIError("OpenAI вернул пустой parsed-объект.")
        return parsed

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception(_is_retryable_openai_error),
        before_sleep=lambda rs: logger.warning(
            "OpenAI retry (text): attempt=%s error=%s", rs.attempt_number, rs.outcome.exception()
        ),
    )
    async def complete_text(self, *, messages: Sequence[ChatCompletionMessageParam]) -> str:
        """Обычное текстовое завершение (резюме, repair промпт)."""
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=list(messages),
            )
        except Exception as exc:
            raise PipelineOpenAIError(f"OpenAI create не удался: {exc}") from exc
        content = resp.choices[0].message.content
        if not content:
            raise PipelineOpenAIError("Пустой content в ответе OpenAI.")
        return content
