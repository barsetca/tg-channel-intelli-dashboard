"""Стадия 5: рекомендации в структурированном виде (потом маппинг в ORM `Recommendation`)."""

from __future__ import annotations

import json

from openai.types.chat import ChatCompletionUserMessageParam

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.prompts.registry import PromptRenderer
from app.ai.schemas.audit import ChannelAuditArtifact
from app.ai.schemas.context import ContextBundle
from app.ai.schemas.recommendations import RecommendationsBundle


async def run_recommendations(
    *,
    bundle: ContextBundle,
    audit: ChannelAuditArtifact,
    client: OpenAIStageClient,
    renderer: PromptRenderer,
    max_items: int = 5,
) -> RecommendationsBundle:
    """Один вызов parse → `RecommendationsBundle` (элементы для UI и БД)."""
    rel = f"{bundle.analyzer_id}/recommendations.j2"
    user_prompt = renderer.render(
        rel,
        audit_json=json.dumps(audit.model_dump(), ensure_ascii=False),
        max_items=max_items,
    )
    messages = [
        ChatCompletionUserMessageParam(
            role="user",
            content=user_prompt,
        ),
    ]
    return await client.parse_structured(messages=messages, response_format=RecommendationsBundle)
