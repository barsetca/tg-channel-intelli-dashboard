"""
AI pipeline для анализа Telegram-каналов (OpenAI + Pydantic + Jinja2 + tenacity).

Основной вход: `ChannelAnalysisPipeline().run(ChannelPipelineInput(...))`.
См. `backend/docs/AI_PIPELINE_ARCHITECTURE.md`.
"""

from app.ai.confidence import ConfidenceSignals, aggregate_confidence, signals_from_parts
from app.ai.orchestration import (
    ChannelAnalysisPipeline,
    PipelineConfigurationError,
    PipelineOpenAIError,
    PipelineRunResult,
    PipelineValidationBlockedError,
)
from app.ai.stages import ChannelPipelineInput, PostSnippet

__all__ = [
    "ChannelAnalysisPipeline",
    "ChannelPipelineInput",
    "PipelineRunResult",
    "PostSnippet",
    "PipelineConfigurationError",
    "PipelineOpenAIError",
    "PipelineValidationBlockedError",
    "aggregate_confidence",
    "signals_from_parts",
    "ConfidenceSignals",
]
