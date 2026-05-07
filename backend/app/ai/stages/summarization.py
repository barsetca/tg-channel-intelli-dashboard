"""Стадия 3: сжатие корпуса постов (упрощённый single-pass reduce вместо полного map-reduce)."""

from __future__ import annotations

from openai.types.chat import ChatCompletionUserMessageParam

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.prompts.registry import PromptRenderer
from app.ai.schemas.context import ContextBundle
from app.ai.schemas.plan import Plan


async def run_summarization(
    *,
    bundle: ContextBundle,
    plan: Plan,
    client: OpenAIStageClient,
    renderer: PromptRenderer,
    max_words: int = 200,
) -> str:
    """
    Если текст короткий — не тратим токены на LLM.
    Иначе один вызов `summarization_reduce.j2` (в полной версии — map по батчам + reduce).
    """
    blob = bundle.combined_posts_text
    if not blob.strip():
        return ""

    rel = f"{bundle.analyzer_id}/summarization_reduce.j2"
    user_prompt = renderer.render(
        rel,
        posts_blob=blob[:50_000],
        max_words=max_words,
    )
    _ = plan  # в map-reduce здесь можно резать по шагам из плана
    return await client.complete_text(
        messages=[ChatCompletionUserMessageParam(role="user", content=user_prompt)],
    )
