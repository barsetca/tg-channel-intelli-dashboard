"""
Оркестратор AI pipeline для аудита канала (analyzer `channel_audit_v1`).

Пример вызова (из сервиса FastAPI после загрузки постов из БД)::

    from datetime import datetime, timezone
    from app.ai.orchestration.pipeline import ChannelAnalysisPipeline
    from app.ai.stages.context_builder import ChannelPipelineInput, PostSnippet

    inp = ChannelPipelineInput(
        user_intent=\"Оцени качество контента и риски для рекламодателя\",
        channel_title=\"Новости\",
        channel_username=\"news\",
        posts=[
            PostSnippet(datetime(2025, 1, 1, tzinfo=timezone.utc), \"Текст поста…\", views=120),
        ],
    )
    result = await ChannelAnalysisPipeline().run(inp)
    # result.audit — Pydantic; result.confidence — 0..1;
    # result.to_result_dict() — для сохранения в Analysis.result_json
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.confidence import aggregate_confidence, signals_from_parts
from app.ai.orchestration.errors import PipelineValidationBlockedError
from app.ai.prompts.registry import prompt_renderer
from app.ai.schemas.audit import ChannelAuditArtifact
from app.ai.schemas.context import ContextBundle
from app.ai.schemas.plan import Plan
from app.ai.schemas.recommendations import RecommendationsBundle
from app.ai.schemas.validation import ValidationResult, ValidationStatus
from app.ai.stages.context_builder import ChannelPipelineInput, build_context_bundle
from app.ai.stages.planner import run_planner
from app.ai.stages.recommendations import run_recommendations
from app.ai.stages.structured_output import run_structured_audit
from app.ai.stages.summarization import run_summarization
from app.ai.stages.validation import run_validation


logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    """Всё, что нужно записать в `Analysis` / отдать в API."""

    analyzer_id: str
    prompt_version: str
    bundle: ContextBundle
    plan: Plan
    validation: ValidationResult
    summary_text: str
    audit: ChannelAuditArtifact
    recommendations: RecommendationsBundle
    confidence: float
    confidence_signals: dict[str, object] = field(default_factory=dict)

    def to_result_dict(self) -> dict[str, object]:
        """Сборка для `Analysis.result_json` (версионирование схемы на стороне API)."""
        return {
            "schema": "channel_audit_pipeline_v1",
            "analyzer_id": self.analyzer_id,
            "prompt_version": self.prompt_version,
            "confidence": self.confidence,
            "confidence_signals": self.confidence_signals,
            "plan": self.plan.model_dump(),
            "validation": {
                "status": self.validation.status.value,
                "reasons": self.validation.reasons,
            },
            "summary": self.summary_text,
            "audit": self.audit.model_dump(),
            "recommendations": self.recommendations.model_dump(),
        }


class ChannelAnalysisPipeline:
    """
    Линейный pipeline: Context → Planner → [RAG] → Validation → Summary →
    Structured → Recommendations.
    Персистенция вынесена: вызывающий код обновляет `Analysis`.
    """

    async def run(self, inp: ChannelPipelineInput) -> PipelineRunResult:
        logger.info(
            "channel_analysis_pipeline.begin analyzer=%s prompt_v=%s posts=%s rag_attached=%s",
            inp.analyzer_id,
            inp.prompt_version,
            len(inp.posts),
            inp.rag_fetcher is not None,
        )
        bundle = build_context_bundle(inp)
        client = OpenAIStageClient()
        renderer = prompt_renderer()

        plan = await run_planner(bundle=bundle, client=client, renderer=renderer)
        logger.info("channel_analysis_pipeline.stage planner use_rag=%s", bool(plan.use_rag))

        # Tool-вызов по плану: опциональный semantic retrieval (Qdrant и т.д.)
        if inp.rag_fetcher is not None and plan.use_rag:
            snippets = await inp.rag_fetcher(plan, bundle)
            bundle.rag_snippets.extend(snippets)
            logger.info(
                "channel_analysis_pipeline.stage rag snippets_added=%s",
                len(snippets),
            )

        validation = run_validation(plan=plan, bundle=bundle)
        logger.info("channel_analysis_pipeline.stage validation_status=%s", validation.status.value)
        if validation.status == ValidationStatus.BLOCK:
            raise PipelineValidationBlockedError(
                "Validation layer заблокировал запуск дорогих стадий.",
                reasons=list(validation.reasons),
            )

        summary_text = await run_summarization(
            bundle=bundle, plan=plan, client=client, renderer=renderer
        )
        logger.info(
            "channel_analysis_pipeline.stage summarization_chars=%s",
            len(summary_text or ""),
        )
        audit, first_try_ok = await run_structured_audit(
            bundle=bundle,
            summary_text=summary_text,
            client=client,
            renderer=renderer,
        )
        recs = await run_recommendations(
            bundle=bundle,
            audit=audit,
            client=client,
            renderer=renderer,
        )

        signals = signals_from_parts(
            data_sufficiency=bundle.data_sufficiency,
            validation=validation,
            structured_json_first_try_ok=first_try_ok,
            plan=plan,
        )
        conf = aggregate_confidence(signals)
        breakdown: dict[str, object] = {
            "data_sufficiency": signals.data_sufficiency,
            "validation_status": signals.validation_status.value,
            "structured_json_first_try_ok": signals.structured_json_first_try_ok,
            "plan_confidence": signals.plan_confidence,
        }

        logger.info(
            "channel_analysis_pipeline.done confidence=%s validation=%s structured_first_try_ok=%s",
            round(conf, 4),
            validation.status.value,
            first_try_ok,
        )

        return PipelineRunResult(
            analyzer_id=inp.analyzer_id,
            prompt_version=inp.prompt_version,
            bundle=bundle,
            plan=plan,
            validation=validation,
            summary_text=summary_text,
            audit=audit,
            recommendations=recs,
            confidence=conf,
            confidence_signals=breakdown,
        )
