"""Стадия 1: LLM Planner — структурированный план (Pydantic + OpenAI parse)."""

from __future__ import annotations

from openai.types.chat import ChatCompletionDeveloperMessageParam, ChatCompletionUserMessageParam

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.prompts.registry import PromptRenderer
from app.ai.schemas.context import ContextBundle
from app.ai.schemas.plan import Plan


async def run_planner(
    *,
    bundle: ContextBundle,
    client: OpenAIStageClient,
    renderer: PromptRenderer,
) -> Plan:
    """Рендерит `planner.j2` и вызывает OpenAI `parse` → `Plan`."""
    # Шаблоны: `prompts/<analyzer_id>/*.j2`; версия — в `bundle.prompt_version`.
    rel = f"{bundle.analyzer_id}/planner.j2"
    user_prompt = renderer.render(
        rel,
        user_intent=bundle.user_intent,
        channel_title=bundle.channel_title,
        channel_username=bundle.channel_username,
        post_count=bundle.post_count,
        data_sufficiency=bundle.data_sufficiency,
        posts_excerpt=bundle.combined_posts_text[:8000],
    )
    messages = [
        ChatCompletionDeveloperMessageParam(
            role="developer",
            content="Ты планировщик. Отвечай только структурированным JSON через инструмент parse.",
        ),
        ChatCompletionUserMessageParam(role="user", content=user_prompt),
    ]
    return await client.parse_structured(messages=messages, response_format=Plan)
