"""
Стадия 0: сборка ContextBundle без LLM.
Обрезает объём текста, считает эвристику достаточности данных, опционально добавляет строку метрик.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.ai.schemas.context import ContextBundle, PostSnippet
from app.ai.schemas.plan import Plan
from app.datetime_compat import ensure_utc_aware
from app.services.channel_metrics import PostMetricRow, compute_channel_metrics


@dataclass
class ChannelPipelineInput:
    """Вход оркестратора: то, что пришло из API/воркера (посты уже из SQL)."""

    user_intent: str
    channel_title: str | None
    channel_username: str | None
    posts: list[PostSnippet]
    analyzer_id: str = "channel_audit_v1"
    prompt_version: str = "v1"
    max_context_chars: int = 24_000
    # Опциональный RAG-tool: вызывается после Planner, если `plan.use_rag` (например Qdrant).
    rag_fetcher: Callable[[Plan, ContextBundle], Awaitable[list[str]]] | None = None


def _format_post(p: PostSnippet) -> str:
    at = ensure_utc_aware(p.posted_at)
    line = f"[{at.date()}] "
    body = (p.text or "").strip()
    return line + (body if body else "(пустой пост)")


def _data_sufficiency(posts: list[PostSnippet]) -> float:
    """
    Простая эвристика 0..1: мало постов или пустые тексты снижают уверенность.
    Не заменяет LLM — используется в aggregate confidence.
    """
    n = len(posts)
    if n == 0:
        return 0.0
    non_empty = sum(1 for p in posts if (p.text or "").strip())
    text_ratio = non_empty / max(n, 1)
    count_part = min(1.0, n / 8.0)
    return round(0.5 * count_part + 0.5 * text_ratio, 4)


def build_context_bundle(inp: ChannelPipelineInput) -> ContextBundle:
    """Склеивает посты, обрезает по `max_context_chars`, считает data_sufficiency."""
    parts: list[str] = []
    total = 0
    for p in sorted(inp.posts, key=lambda x: ensure_utc_aware(x.posted_at)):
        chunk = _format_post(p) + "\n"
        if total + len(chunk) > inp.max_context_chars:
            parts.append("… [контекст усечён по лимиту символов]")
            break
        parts.append(chunk)
        total += len(chunk)

    combined = "\n".join(parts)
    suff = _data_sufficiency(inp.posts)

    metrics_text: str | None = None
    rows = []
    for p in inp.posts:
        rows.append(
            PostMetricRow(posted_at=ensure_utc_aware(p.posted_at), views=p.views, forwards=None),
        )
    if rows:
        snap = compute_channel_metrics(rows, now_utc=datetime.now(timezone.utc))
        ep = snap.engagement_proxy
        metrics_text = (
            f"posts_used={snap.posts_used}; avg_views={snap.avg_views}; "
            f"posting_frequency={snap.posting_frequency}; engagement_proxy={ep:.4f}; "
            f"activity_score={snap.activity_score:.1f}; "
            f"consistency_score={snap.consistency_score:.1f}"
        )

    return ContextBundle(
        analyzer_id=inp.analyzer_id,
        prompt_version=inp.prompt_version,
        user_intent=inp.user_intent,
        channel_title=inp.channel_title,
        channel_username=inp.channel_username,
        combined_posts_text=combined,
        post_count=len(inp.posts),
        data_sufficiency=suff,
        metrics_text=metrics_text,
        rag_snippets=[],
    )
