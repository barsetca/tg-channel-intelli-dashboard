"""
Стадия 4: структурированный JSON (аудит канала).
Сначала `parse`; при любой ошибке парсинга/контракта — одна попытка **repair**.
"""

from __future__ import annotations

from openai.types.chat import ChatCompletionUserMessageParam

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.prompts.registry import PromptRenderer
from app.ai.schemas.audit import ChannelAuditArtifact
from app.ai.schemas.context import ContextBundle


async def _repair(
    *,
    client: OpenAIStageClient,
    renderer: PromptRenderer,
    bundle: ContextBundle,
    broken: str,
    err: str,
) -> ChannelAuditArtifact:
    """Один узкий вызов для исправления JSON под схему `ChannelAuditArtifact`."""
    rel = f"{bundle.analyzer_id}/json_repair.j2"
    prompt = renderer.render(
        rel,
        model_name=ChannelAuditArtifact.__name__,
        validation_errors=err,
        broken_json=broken[:12_000],
    )
    fixed = await client.complete_text(
        messages=[ChatCompletionUserMessageParam(role="user", content=prompt)],
    )
    return ChannelAuditArtifact.model_validate_json(fixed.strip())


async def run_structured_audit(
    *,
    bundle: ContextBundle,
    summary_text: str,
    client: OpenAIStageClient,
    renderer: PromptRenderer,
) -> tuple[ChannelAuditArtifact, bool]:
    """
    Возвращает (артефакт, first_try_ok).
    `first_try_ok` участвует в aggregate confidence.
    """
    rel = f"{bundle.analyzer_id}/structured_audit.j2"
    user_prompt = renderer.render(
        rel,
        summary_text=summary_text,
        metrics_text=bundle.metrics_text or "",
        rag_snippets=bundle.rag_snippets,
    )
    messages = [
        ChatCompletionUserMessageParam(
            role="user",
            content=(
                user_prompt
                + "\n\nВерни JSON строго по схеме ChannelAuditArtifact."
            ),
        ),
    ]
    try:
        artifact = await client.parse_structured(
            messages=messages,
            response_format=ChannelAuditArtifact,
        )
        return artifact, True
    except Exception as exc:
        repaired = await _repair(
            client=client,
            renderer=renderer,
            bundle=bundle,
            broken=user_prompt,
            err=str(exc),
        )
        return repaired, False
