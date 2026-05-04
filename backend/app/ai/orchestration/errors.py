"""Доменные ошибки AI pipeline (маппинг в `Analysis.status` на стороне API)."""

from __future__ import annotations


class PipelineError(Exception):
    """Базовая ошибка стадии pipeline."""


class PipelineConfigurationError(PipelineError):
    """Нет API-ключа, промпта или схемы для выбранного `analyzer_id`."""


class PipelineValidationBlockedError(PipelineError):
    """ValidationLayer вернул `block` — дальнейшие LLM-стадии не выполняются."""

    def __init__(self, message: str, *, reasons: list[str]) -> None:
        super().__init__(message)
        self.reasons = reasons


class PipelineOpenAIError(PipelineError):
    """Исчерпаны ретраи или неожиданный ответ OpenAI."""
