"""
Сценарий 1 — шаг AI Planner: LLM нормализует запрос пользователя в ``SearchPlannerOutput``.

Без ``OPENAI_API_KEY`` используется детерминированный fallback из полей формы.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai.types.chat import ChatCompletionDeveloperMessageParam, ChatCompletionUserMessageParam

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.schemas.search_planner import SearchPlannerOutput
from app.ai.orchestration.errors import PipelineConfigurationError, PipelineOpenAIError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _preview(text: str | None, *, max_len: int = 140) -> str:
    s = (text or "").replace("\n", " ").strip()
    return s if len(s) <= max_len else f"{s[: max_len - 1]}…"


def _fallback_planner(user: dict[str, Any]) -> SearchPlannerOutput:
    topic = str(user.get("topic", "")).strip()
    return SearchPlannerOutput(
        search_topic=topic or "channels",
        min_subscribers=user.get("min_subscribers"),
        max_subscribers=user.get("max_subscribers"),
        count=int(user.get("count", 20) or 20),
        language=(str(user.get("language") or "").strip() or None),
        region_country=(str(user.get("region_country") or "").strip() or None),
        confidence="medium",
    )


def merge_planner_with_user_request(user: dict[str, Any], planner: SearchPlannerOutput) -> dict[str, Any]:
    """
    Слияние: планировщик задаёт нишу и мягкие границы, форма пользователя — жёсткий потолок по count
    и пересечение диапазонов подписчиков.
    """
    source = str(user.get("search_source") or "saved_catalog")
    max_count = 30 if source == "telegram_live" else 10_000
    user_count = user.get("count")
    if user_count is None:
        count = max(1, min(planner.count, max_count))
    else:
        u_count = max(1, min(max_count, int(user_count or 20)))
        count = max(1, min(u_count, planner.count, max_count))

    topic = (planner.search_topic or "").strip() or str(user.get("topic", "")).strip()

    def _imax(a: int | None, b: int | None) -> int | None:
        if a is None:
            return b
        if b is None:
            return a
        return max(a, b)

    def _imin(a: int | None, b: int | None) -> int | None:
        if a is None:
            return b
        if b is None:
            return a
        return min(a, b)

    u_min = user.get("min_subscribers")
    u_max = user.get("max_subscribers")
    eff_min = _imax(u_min if isinstance(u_min, int) else None, planner.min_subscribers)
    eff_max = _imin(u_max if isinstance(u_max, int) else None, planner.max_subscribers)
    if eff_min is not None and eff_max is not None and eff_max < eff_min:
        eff_max = u_max if isinstance(u_max, int) else planner.max_subscribers

    lang = planner.language or (str(user.get("language") or "").strip() or None)
    region = planner.region_country or (str(user.get("region_country") or "").strip() or None)

    return {
        "search_topic": topic,
        "count": count,
        "min_subscribers": eff_min,
        "max_subscribers": eff_max,
        "language": lang,
        "region_country": region,
        "channel_type": user.get("channel_type", "all"),
        "extra_conditions": user.get("extra_conditions"),
        "search_source": user.get("search_source", "saved_catalog"),
        "planner_confidence": planner.confidence,
    }


async def plan_channel_search(settings: Settings, user_payload: dict[str, Any]) -> SearchPlannerOutput:
    if not settings.openai_api_key:
        out = _fallback_planner(user_payload)
        logger.info("channel_search_planner: OPENAI отсутствует — fallback planner topic=%r", out.search_topic)
        return out

    try:
        client = OpenAIStageClient(settings)
    except PipelineConfigurationError:
        return _fallback_planner(user_payload)

    user_blob = json.dumps(user_payload, ensure_ascii=False, default=str)
    messages = [
        ChatCompletionDeveloperMessageParam(
            role="developer",
            content=(
                "Ты планировщик поиска Telegram-каналов. По JSON формы пользователя верни структурированный план: "
                "search_topic (краткая нишевая тема для полнотекстового / Telegram search), min/max подписчиков, "
                "count (сколько каналов запросить), language (ISO/короткий код или null), region_country или null, "
                "confidence. Уважай явные числовые фильтры пользователя; search_topic должен быть конкретнее "
                "общих фраз если extra_conditions задаёт нишу."
            ),
        ),
        ChatCompletionUserMessageParam(
            role="user",
            content=f"Запрос пользователя (JSON):\n{user_blob}",
        ),
    ]
    try:
        out = await client.parse_structured(messages=messages, response_format=SearchPlannerOutput)
        logger.info(
            "channel_search_planner LLM ok confidence=%s search_topic=%r count=%s",
            out.confidence,
            _preview(out.search_topic),
            out.count,
        )
        return out
    except PipelineOpenAIError as exc:
        logger.warning("channel_search_planner: OpenAI недоступен (%s) — fallback", exc)
        return _fallback_planner(user_payload)
