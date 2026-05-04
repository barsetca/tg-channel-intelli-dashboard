"""
Бизнес-логика intelligence API: поиск, детали канала, анализ, сводка, сравнение, экспорт.

Тяжёлые вызовы OpenAI/Qdrant изолированы — эндпоинты остаются тонкими обёртками.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.orchestration.errors import PipelineValidationBlockedError
from app.ai.orchestration.pipeline import ChannelAnalysisPipeline
from app.ai.prompts.registry import prompt_renderer
from app.ai.schemas.plan import Plan
from app.ai.schemas.context import PostSnippet
from app.ai.stages.context_builder import ChannelPipelineInput, build_context_bundle
from app.ai.stages.summarization import run_summarization
from app.core.config import Settings, get_settings
from app.models.analysis import Analysis
from app.models.post import Post
from app.orchestration.coordinator import OrchestrationCoordinator
from app.repositories.channel_repository import ChannelRepository
from app.schemas.intelligence import (
    AnalyzeChannelResponse,
    BackgroundSearchJob,
    ChannelCard,
    ChannelDetail,
    CompareChannelRow,
    CompareChannelsRequest,
    CompareChannelsResponse,
    ManualReviewFlags,
    SearchChannelsRequest,
    SearchChannelsResponse,
    SimilarChannelItem,
    SimilarChannelsResponse,
    SummarizePostsRequest,
    SummarizePostsResponse,
)
from app.services.vector_service import VectorService


class IntelligenceService:
    """Сервис доменных сценариев dashboard (без привязки к HTTP)."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        coordinator: OrchestrationCoordinator | None = None,
        telethon_live_available: bool = False,
        telethon_startup_failure: str | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._channels = ChannelRepository(session)
        self._coordinator = coordinator
        self._telethon_live_available = telethon_live_available
        self._telethon_startup_failure = telethon_startup_failure

    def _telegram_live_unavailable_detail(self) -> str:
        """Пояснение для ``background_job`` когда live-поиск недоступен (без постановки в очередь)."""
        if not (self._settings.telegram_api_id and self._settings.telegram_api_hash):
            return "Telegram (live) недоступен: задайте TELEGRAM_API_ID и TELEGRAM_API_HASH."
        base = (
            "Telegram (live) недоступен: при старте API не удалось поднять сессию Telethon. "
            "Запрос телефона при поиске не выполняется — сначала авторизуйтесь через "
            "POST /api/v1/telegram/auth/start → /auth/code (при 2FA — /auth/password), "
            "либо задайте TELEGRAM_SESSION / валидный .session и перезапустите API."
        )
        if self._telethon_startup_failure:
            return f"{base} Подробности: {self._telethon_startup_failure}"
        return base

    def _manual_review_too_broad(self, body: SearchChannelsRequest) -> ManualReviewFlags | None:
        """Сценарий 8: слишком общий запрос без уточняющих фильтров."""
        t = body.topic.strip().lower()
        vague_topics = {
            "каналы",
            "лучшие каналы",
            "топ каналы",
            "все",
            "интересное",
            "подборка",
        }
        has_extra_filters = (
            body.min_subscribers is not None
            or body.max_subscribers is not None
            or bool(body.language)
            or bool(body.region_country)
            or bool((body.extra_conditions or "").strip())
        )
        if t in vague_topics and not has_extra_filters:
            return ManualReviewFlags(
                needs_review=True,
                reason="Недостаточно параметров для автоматического поиска",
                hints=[
                    "Уточните тематику (нишу), а не общие формулировки",
                    "Задайте диапазон подписчиков или регион",
                    "Добавьте дополнительные условия в свободной форме",
                ],
            )
        if len(t) < 3 and not has_extra_filters:
            return ManualReviewFlags(
                needs_review=True,
                reason="Тематика слишком короткая или пустая",
                hints=["Введите не менее 3 символов темы или добавьте фильтры"],
            )
        return None

    async def search_channels(self, body: SearchChannelsRequest) -> SearchChannelsResponse:
        """Сценарий 1: каталог в SQLite + сценарий 8 при необходимости."""
        review = self._manual_review_too_broad(body)
        if review is not None:
            return SearchChannelsResponse(
                channels=[],
                manual_review=review,
                normalized_filters=body.model_dump(),
                background_job=None,
            )

        if body.search_source == "telegram_live":
            if self._coordinator is None:
                return SearchChannelsResponse(
                    channels=[],
                    manual_review=None,
                    normalized_filters=body.model_dump(),
                    background_job=BackgroundSearchJob(
                        job_id=str(uuid.uuid4()),
                        status="failed",
                        detail="OrchestrationCoordinator не смонтирован (lifespan приложения).",
                    ),
                )
            if not self._telethon_live_available:
                return SearchChannelsResponse(
                    channels=[],
                    manual_review=None,
                    normalized_filters=body.model_dump(),
                    background_job=BackgroundSearchJob(
                        job_id=str(uuid.uuid4()),
                        status="failed",
                        detail=self._telegram_live_unavailable_detail(),
                    ),
                )
            job_id = await self._coordinator.schedule_telegram_channel_discovery(
                payload=body.model_dump(),
            )
            return SearchChannelsResponse(
                channels=[],
                manual_review=None,
                normalized_filters=body.model_dump(),
                background_job=BackgroundSearchJob(
                    job_id=job_id,
                    status="queued",
                    detail="Задание поставлено в очередь: Telethon → SQLite → metrics → AI → vector.",
                ),
            )

        rows = await self._channels.search_catalog(
            topic=body.topic,
            limit=body.count,
            min_subscribers=body.min_subscribers,
            max_subscribers=body.max_subscribers,
            language=body.language,
            region_country=body.region_country,
            new_only=body.channel_type == "new_only",
        )
        cards = [ChannelCard.model_validate(r) for r in rows]
        return SearchChannelsResponse(
            channels=cards,
            manual_review=None,
            normalized_filters=body.model_dump(),
            background_job=None,
        )

    async def get_channel_detail(self, channel_id: int) -> ChannelDetail | None:
        """Сценарий 2 (часть): карточка канала из БД."""
        row = await self._channels.get_by_id(channel_id)
        if row is None:
            return None
        return ChannelDetail.model_validate(row)

    async def run_channel_analysis(
        self,
        *,
        channel_id: int,
        user_intent: str,
    ) -> tuple[AnalyzeChannelResponse, None] | tuple[None, str]:
        """
        Сценарий 2: AI-анализ канала, результат в `Analysis`.

        Возвращает либо (response, None), либо (None, error_code) если канал не найден.
        """
        ch = await self._channels.get_by_id(channel_id)
        if ch is None:
            return None, "not_found"

        res_posts = await self._session.execute(
            select(Post)
            .where(Post.channel_id == channel_id)
            .order_by(Post.posted_at.desc())
            .limit(50),
        )
        posts = list(res_posts.scalars())
        snippets: list[PostSnippet] = [
            PostSnippet(p.posted_at, p.text or "", views=p.views_count) for p in reversed(posts)
        ]

        inp = ChannelPipelineInput(
            user_intent=user_intent,
            channel_title=ch.title,
            channel_username=ch.username,
            posts=snippets,
        )
        analysis = Analysis(
            channel_id=ch.id,
            analyzer_id=inp.analyzer_id,
            status="running",
            input_refs_json={"post_count": len(snippets)},
        )
        self._session.add(analysis)
        await self._session.flush()

        try:
            pipeline = ChannelAnalysisPipeline()
            result = await pipeline.run(inp)
            analysis.status = "completed"
            analysis.result_json = result.to_result_dict()
            analysis.llm_model = self._settings.openai_chat_model
            msg = "Анализ завершён; результат в result_json записи Analysis."
        except PipelineValidationBlockedError as e:
            analysis.status = "blocked_validation"
            analysis.result_json = {"reasons": e.reasons, "validation": "block"}
            analysis.error_detail = "; ".join(e.reasons)
            msg = "Валидация заблокировала LLM-стадии; уточните запрос или данные канала."
        except Exception as e:  # noqa: BLE001 — гранулярные коды добавятся по мере зрелости API
            analysis.status = "failed"
            analysis.error_detail = str(e)
            msg = f"Ошибка пайплайна: {e!s}"

        await self._session.commit()
        await self._session.refresh(analysis)

        api_status = analysis.status if analysis.status in (
            "completed",
            "blocked_validation",
            "failed",
        ) else "failed"
        return (
            AnalyzeChannelResponse(
                analysis_id=analysis.id,
                channel_id=ch.id,
                status=api_status,
                message=msg,
            ),
            None,
        )

    async def summarize_recent_posts(
        self,
        *,
        channel_id: int,
        body: SummarizePostsRequest,
    ) -> tuple[SummarizePostsResponse, None] | tuple[None, str]:
        """Сценарий 3: сводка последних N постов через стадию summarization."""
        ch = await self._channels.get_by_id(channel_id)
        if ch is None:
            return None, "not_found"

        res_posts = await self._session.execute(
            select(Post)
            .where(Post.channel_id == channel_id)
            .order_by(Post.posted_at.desc())
            .limit(body.post_limit),
        )
        posts = list(res_posts.scalars())
        snippets = [
            PostSnippet(p.posted_at, p.text or "", views=p.views_count) for p in reversed(posts)
        ]
        inp = ChannelPipelineInput(
            user_intent="Краткая сводка последних постов",
            channel_title=ch.title,
            channel_username=ch.username,
            posts=snippets,
        )
        bundle = build_context_bundle(inp)
        plan = Plan(use_rag=False)
        client = OpenAIStageClient()
        renderer = prompt_renderer()
        summary = await run_summarization(
            bundle=bundle,
            plan=plan,
            client=client,
            renderer=renderer,
        )

        return (
            SummarizePostsResponse(
                channel_id=ch.id,
                posts_used=len(snippets),
                summary=summary,
                stored_analysis_hint=(
                    "Можно сохранить как Analysis, analyzer_id=channel_posts_summary_v1"
                ),
            ),
            None,
        )

    async def compare_channels(
        self,
        body: CompareChannelsRequest,
    ) -> CompareChannelsResponse | None:
        """Сценарий 5: сравнение метрик по выбранным каналам."""
        rows_out: list[CompareChannelRow] = []
        for cid in body.channel_ids:
            ch = await self._channels.get_by_id(cid)
            if ch is None:
                return None
            rows_out.append(
                CompareChannelRow(
                    channel_id=ch.id,
                    title=ch.title,
                    username=ch.username,
                    subscriber_count=ch.subscriber_count,
                    posts_per_week_estimate=ch.posts_per_week_estimate,
                    primary_topic=ch.primary_topic,
                ),
            )
        notes = (
            "Сравнение по метрикам из БД. Для narrative-слоя подключите отдельный LLM-шаг "
            "(см. AI_PIPELINE_ARCHITECTURE.md)."
        )
        return CompareChannelsResponse(rows=rows_out, comparison_notes=notes)

    async def export_channels_payload(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Сериализация каналов для экспорта (сценарий 7)."""
        rows = await self._channels.list_all(limit=limit, offset=0)
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "telegram_id": r.telegram_id,
                    "username": r.username,
                    "title": r.title,
                    "description": r.description,
                    "subscriber_count": r.subscriber_count,
                    "primary_topic": r.primary_topic,
                    "last_post_at": r.last_post_at.isoformat() if r.last_post_at else None,
                },
            )
        return out

    def channels_to_csv(self, rows: Sequence[dict[str, Any]]) -> str:
        """Преобразование списка dict в CSV (UTF-8)."""
        if not rows:
            return ""
        buf = io.StringIO()
        fieldnames = list(rows[0].keys())
        w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return buf.getvalue()

    def channels_to_json_bytes(self, rows: Sequence[dict[str, Any]]) -> bytes:
        return json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")

    async def find_similar_channels(
        self,
        *,
        seed_channel_id: int,
        vector: VectorService,
        limit: int = 10,
    ) -> tuple[SimilarChannelsResponse, None] | tuple[None, str]:
        """Сценарий 6: embedding профиля + поиск по постам, агрегация по channel_id."""
        ch = await self._channels.get_by_id(seed_channel_id)
        if ch is None:
            return None, "not_found"

        profile = "\n".join(
            x
            for x in (
                ch.title or "",
                ch.description or "",
                ch.primary_topic or "",
            )
            if x.strip()
        )
        if not profile.strip():
            profile = ch.username or f"channel_{ch.id}"

        hits = await vector.semantic_search(
            query=profile,
            limit=50,
            content_type="post",
        )
        by_channel: dict[int, float] = {}
        for h in hits:
            props = h.properties
            cid = props.get("channel_id")
            if cid is None:
                continue
            ic = int(cid)
            if ic == seed_channel_id or ic < 0:
                continue
            sc = h.score if h.score is not None else 0.0
            prev = by_channel.get(ic)
            if prev is None or sc > prev:
                by_channel[ic] = sc

        ranked = sorted(by_channel.items(), key=lambda x: x[1], reverse=True)[:limit]
        similar: list[SimilarChannelItem] = []
        for cid, score in ranked:
            row = await self._channels.get_by_id(cid)
            similar.append(
                SimilarChannelItem(
                    channel_id=cid,
                    score=score,
                    title=row.title if row else None,
                    username=row.username if row else None,
                ),
            )
        return SimilarChannelsResponse(seed_channel_id=seed_channel_id, similar=similar), None
