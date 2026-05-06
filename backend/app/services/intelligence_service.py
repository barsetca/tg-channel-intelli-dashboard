"""
Бизнес-логика intelligence API: поиск, детали канала, анализ, сводка, сравнение, экспорт.

Тяжёлые вызовы OpenAI/Qdrant изолированы — эндпоинты остаются тонкими обёртками.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionDeveloperMessageParam, ChatCompletionUserMessageParam
from qdrant_client.models import PayloadSchemaType
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.clients.openai_chat import OpenAIStageClient
from app.ai.orchestration.errors import PipelineValidationBlockedError
from app.ai.orchestration.pipeline import ChannelAnalysisPipeline
from app.ai.prompts.registry import prompt_renderer
from app.ai.schemas.context import PostSnippet
from app.ai.schemas.extra_conditions_review import ExtraConditionsReviewOutput
from app.ai.schemas.plan import Plan
from app.ai.schemas.search_planner import SearchPlannerOutput
from app.ai.stages.context_builder import ChannelPipelineInput, build_context_bundle
from app.ai.stages.summarization import run_summarization
from app.core.config import Settings, get_settings
from app.datetime_compat import ensure_utc_aware
from app.integrations.qdrant_client import QdrantStore
from app.integrations.telethon.dto import TelegramPostBrief
from app.integrations.telethon.exceptions import TelegramTelethonError
from app.integrations.telethon.user_session_service import TelethonUserSessionService
from app.models.analysis import Analysis
from app.models.audit_run import AuditRun
from app.models.audit_run_item import AuditRunItem
from app.models.channel import Channel
from app.models.post import Post
from app.orchestration.coordinator import OrchestrationCoordinator
from app.repositories.channel_repository import ChannelRepository
from app.schemas.intelligence import (
    AnalyzeChannelResponse,
    ChannelAnalysisHistoryItem,
    ChannelAnalysisReport,
    ContentStrategyReport,
    ToneOfVoiceReport,
    SavedChannelAnalysisDetail,
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
    SummarizePostsByHandleRequest,
    SummarizePostsResponse,
    AnalyzeChannelByHandleRequest,
)
from app.services.channel_search_planner import merge_planner_with_user_request, plan_channel_search
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)
_URL_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"#([\w_]{2,64})", flags=re.UNICODE)
_MENTION_RE = re.compile(r"@([\w_]{3,64})", flags=re.UNICODE)


@dataclass
class PostForAnalysis:
    message_id: int
    published_at: datetime
    clean_text: str
    urls: list[str]
    hashtags: list[str]
    mentions: list[str]
    post_type: str
    has_media: bool
    media_type: str | None
    is_forwarded: bool
    is_reply: bool
    language: str


def _sync_at_sort_key(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return ensure_utc_aware(dt)


def channel_display_ref(ch: Channel) -> str:
    """Человекочитаемая метка канала для UI: @username, сохранённая ссылка или запасной id."""
    if ch.username:
        u = ch.username.strip().lstrip("@")
        if u:
            return f"@{u}"
    slug = (ch.invite_slug or "").strip()
    if slug:
        return slug
    return f"#{ch.id}"


def analysis_status_message(
    *,
    analysis_id: int,
    label: str,
    status: str,
    error_detail: str | None,
) -> str:
    """Две строки: заголовок статуса и пояснение (без технических имён полей БД)."""
    if status == "completed":
        return (
            f"Отчёт №{analysis_id} · Канал {label} · Статус: завершён.\n"
            "Анализ завершён. Отчёт сохранён."
        )
    if status == "blocked_validation":
        return (
            f"Отчёт №{analysis_id} · Канал {label} · Статус: проверка не пройдена.\n"
            "Валидация заблокировала этапы анализа. Уточните запрос или данные канала."
        )
    if status == "failed":
        err = (error_detail or "").strip() or "неизвестная ошибка"
        return (
            f"Отчёт №{analysis_id} · Канал {label} · Статус: ошибка.\n"
            f"Не удалось завершить анализ: {err}"
        )
    extra = f"\n{error_detail}" if error_detail else ""
    return f"Отчёт №{analysis_id} · Канал {label} · Статус: {status}.{extra}"


class IntelligenceService:
    """Сервис доменных сценариев dashboard (без привязки к HTTP)."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        *,
        coordinator: OrchestrationCoordinator | None = None,
        telegram: TelethonUserSessionService | None = None,
        telethon_live_available: bool = False,
        telethon_startup_failure: str | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._channels = ChannelRepository(session)
        self._coordinator = coordinator
        self._telegram = telegram
        self._telethon_live_available = telethon_live_available
        self._telethon_startup_failure = telethon_startup_failure

    def _telegram_live_unavailable_detail(self) -> str:
        """Текст ``background_job``, если live-поиск недоступен (очередь не ставится)."""
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

    async def _review_extra_conditions(
        self,
        body: SearchChannelsRequest,
    ) -> ManualReviewFlags | None:
        extra = (body.extra_conditions or "").strip()
        if not extra:
            return None

        if not self._settings.openai_api_key:
            return None

        try:
            client = OpenAIStageClient(self._settings)
            user_blob = json.dumps(body.model_dump(mode="json"), ensure_ascii=False, default=str)
            server_now_iso = datetime.utcnow().isoformat() + "Z"
            out = await client.parse_structured(
                messages=[
                    ChatCompletionDeveloperMessageParam(
                        role="developer",
                        content=(
                            "Ты валидатор формы поиска Telegram-каналов. "
                            "Верни JSON строго по схеме: needs_review, reason, last_post_at_lte. "
                            "Текущее время: "
                            f"{server_now_iso}. "
                            "Правила: "
                            "1) needs_review=true ТОЛЬКО при явном конфликте темы поиска "
                            "и доп. условий. "
                            "2) Все ограничения по датам ИГНОРИРУЙ при валидации: "
                            "даты проверяются отдельно не через LLM. "
                            "3) Не извлекай даты и оставляй last_post_at_lte = null. "
                            "4) Если конфликтов темы нет — needs_review=false, reason=''. "
                            "5) Ошибку по дате выдавай только если дата в будущем "
                            "относительно server_now. "
                            "6) Фразу вида "
                            "'Тема поиска ... не соответствует дополнительным условиям' "
                            "используй только при реальном тематическом конфликте. "
                            "Пример конфликта: topic='Путешествия', "
                            "extra='Найди канал про финансы'."
                        ),
                    ),
                    ChatCompletionUserMessageParam(
                        role="user",
                        content=f"Форма поиска:\n{user_blob}",
                    ),
                ],
                response_format=ExtraConditionsReviewOutput,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("extra_conditions_review fallback due to OpenAI error: %s", exc)
            return None

        reason_lc = (out.reason or "").lower()
        has_no_conflict_phrase = (
            "не противоречит теме" in reason_lc
            or "конфликтов темы нет" in reason_lc
        )
        if out.needs_review and has_no_conflict_phrase:
            logger.info(
                "extra_conditions_review: drop false-positive needs_review, reason=%r",
                out.reason,
            )
            out.needs_review = False
            out.reason = ""

        if out.needs_review:
            reason_text = (out.reason or "").strip() or "Противоречивые условия поиска"
            if not reason_text.lower().startswith("обнаружено несоответствие данных"):
                reason_text = f"Обнаружено несоответствие данных: {reason_text}"
            return ManualReviewFlags(
                needs_review=True,
                reason=reason_text,
                hints=["Уточните тему и дополнительные условия, чтобы они не конфликтовали"],
            )
        return None

    async def _record_catalog_search_audit(
        self,
        body: SearchChannelsRequest,
        planner: SearchPlannerOutput,
        rows: list[Channel],
    ) -> None:
        """Сценарий 1 шаг 5: audit_runs + audit_run_items для поиска по локальному каталогу."""
        audit = AuditRun(
            audit_kind="channel_discovery",
            status="completed",
            raw_user_input_json=body.model_dump(mode="json"),
            planner_output_json=planner.model_dump(mode="json"),
            result_summary_json={"source": "saved_catalog", "channels_returned": len(rows)},
        )
        self._session.add(audit)
        await self._session.flush()
        for i, row in enumerate(rows):
            snap = ChannelCard.model_validate(row).model_dump(mode="json")
            self._session.add(
                AuditRunItem(
                    audit_run_id=int(audit.id),
                    entity_kind="channel_candidate",
                    channel_id=row.id,
                    display_order=i,
                    relevance_score=Decimal("0"),
                    snapshot_json=snap,
                    telegram_username_fallback=row.username,
                )
            )
        await self._session.commit()

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
        extra_review = await self._review_extra_conditions(body)
        if extra_review is not None:
            return SearchChannelsResponse(
                channels=[],
                manual_review=extra_review,
                normalized_filters=body.model_dump(),
                background_job=None,
            )
        last_post_at_gte: datetime | None = None
        last_post_at_lte: datetime | None = None
        if body.last_post_from is not None:
            last_post_at_gte = datetime.combine(body.last_post_from, time.min)
        if body.last_post_to is not None:
            last_post_at_lte = datetime.combine(body.last_post_to, time.max)

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
            live_payload = body.model_dump()
            live_payload["min_subscribers"] = None
            live_payload["max_subscribers"] = None
            job_id = await self._coordinator.schedule_telegram_channel_discovery(
                payload=live_payload,
            )
            logger.info("Конвейер обнаружения Telegram (оркестратор).")
            logger.info(
                "Статус обновляется каждые ~1.5 с через GET /api/v1/orchestration/jobs/…; "
                "этапы: job_dequeued, stage_begin / stage_end."
            )
            logger.info("Идентификатор задания оркестратора: job_id=%s", job_id)
            logger.info("Задание в очереди: Telethon → SQLite → metrics → AI → vector.")
            return SearchChannelsResponse(
                channels=[],
                manual_review=None,
                normalized_filters=body.model_dump(),
                background_job=BackgroundSearchJob(
                    job_id=job_id,
                    status="queued",
                    detail=(
                        "Задание в очереди: Telethon → SQLite → metrics → AI → vector."
                    ),
                ),
            )

        planner = await plan_channel_search(self._settings, body.model_dump(mode="json"))
        merged = merge_planner_with_user_request(body.model_dump(mode="json"), planner)
        planner_topic = str(merged.get("search_topic") or body.topic).strip()
        user_topic = body.topic.strip()
        limit_n = int(merged.get("count") or body.count or 20)
        catalog_limit: int | None = None if body.count is None else limit_n
        eff_sort_by = "last_sync_at" if merged.get("channel_type") == "new_only" else body.sort_by
        eff_sort_order = "desc" if merged.get("channel_type") == "new_only" else body.sort_order
        catalog_kw: dict[str, Any] = {
            "limit": catalog_limit,
            "min_subscribers": merged.get("min_subscribers"),
            "max_subscribers": merged.get("max_subscribers"),
            "language": merged.get("language"),
            "region_country": merged.get("region_country"),
            "new_only": merged.get("channel_type") == "new_only",
            "sort_by": eff_sort_by,
            "sort_order": eff_sort_order,
            "username_query": body.username_query,
            "last_post_at_gte": last_post_at_gte,
            "last_post_at_lte": last_post_at_lte,
        }
        topics_tried = [planner_topic]
        rows = await self._channels.search_catalog(topic=planner_topic, **catalog_kw)
        # EN↔RU у планировщика: сливаем результаты по его теме и по исходной строке пользователя.
        if user_topic and user_topic.lower() != planner_topic.lower():
            topics_tried.append(user_topic)
            rows_user = await self._channels.search_catalog(topic=user_topic, **catalog_kw)
            by_id: dict[int, Channel] = {}
            for r in list(rows) + list(rows_user):
                by_id[r.id] = r
            merged_rows = list(by_id.values())
            rev = eff_sort_order == "desc"
            if eff_sort_by == "last_sync_at":
                merged_rows.sort(
                    key=lambda ch: (
                        ch.last_sync_at is None,
                        _sync_at_sort_key(ch.last_sync_at),
                        ch.subscriber_count or 0,
                        ch.id,
                    ),
                    reverse=rev,
                )
            else:
                merged_rows.sort(
                    key=lambda ch: (
                        ch.subscriber_count is None,
                        ch.subscriber_count or 0,
                        _sync_at_sort_key(ch.last_sync_at),
                        ch.id,
                    ),
                    reverse=rev,
                )
            rows = merged_rows if catalog_limit is None else merged_rows[:catalog_limit]
        cards = [ChannelCard.model_validate(r) for r in rows]
        try:
            await self._record_catalog_search_audit(body, planner, rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Не удалось записать audit_run для поиска по каталогу: %s", exc)
        normalized: dict[str, Any] = {
            **body.model_dump(mode="json"),
            "planner": planner.model_dump(mode="json"),
            "merged_search_params": merged,
            "saved_catalog_topics_tried": topics_tried,
            "extra_conditions_applied": {
                "username_query": body.username_query,
                "last_post_at_gte": last_post_at_gte.isoformat() if last_post_at_gte else None,
                "last_post_at_lte": last_post_at_lte.isoformat() if last_post_at_lte else None,
            },
        }
        return SearchChannelsResponse(
            channels=cards,
            manual_review=None,
            normalized_filters=normalized,
            background_job=None,
        )

    async def get_channel_detail(self, channel_id: int) -> ChannelDetail | None:
        """Сценарий 2 (часть): карточка канала из БД."""
        row = await self._channels.get_by_id(channel_id)
        if row is None:
            return None
        return ChannelDetail.model_validate(row)

    async def list_channel_analysis_history(
        self,
        *,
        channel_id: int | None,
        limit: int,
    ) -> list[ChannelAnalysisHistoryItem]:
        stmt = select(Analysis).where(Analysis.channel_id.is_not(None))
        if channel_id is not None:
            stmt = stmt.where(Analysis.channel_id == channel_id)
        stmt = stmt.order_by(desc(Analysis.created_at)).limit(limit)
        res = await self._session.execute(stmt)
        rows = list(res.scalars().all())
        channel_ids = sorted({int(r.channel_id) for r in rows if r.channel_id is not None})
        channel_by_id: dict[int, Channel] = {}
        if channel_ids:
            channel_res = await self._session.execute(select(Channel).where(Channel.id.in_(channel_ids)))
            channel_by_id = {int(ch.id): ch for ch in channel_res.scalars().all()}
        return [
            ChannelAnalysisHistoryItem(
                id=int(r.id),
                channel_id=int(r.channel_id) if r.channel_id is not None else None,
                channel_display_ref=(
                    channel_display_ref(channel_by_id[int(r.channel_id)])
                    if r.channel_id is not None and int(r.channel_id) in channel_by_id
                    else None
                ),
                status=str(r.status),
                analyzer_id=str(r.analyzer_id),
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def get_saved_channel_analysis(
        self,
        *,
        analysis_id: int,
    ) -> tuple[SavedChannelAnalysisDetail | None, str | None]:
        res = await self._session.execute(select(Analysis).where(Analysis.id == analysis_id))
        analysis = res.scalar_one_or_none()
        if analysis is None or analysis.channel_id is None:
            return None, "not_found"
        ch = await self._channels.get_by_id(int(analysis.channel_id))
        if ch is None:
            return None, "channel_not_found"
        res_posts = await self._session.execute(
            select(Post)
            .where(Post.channel_id == ch.id)
            .order_by(Post.posted_at.desc())
            .limit(50),
        )
        posts = list(res_posts.scalars())
        report = self._build_channel_analysis_report(
            channel=ch,
            posts=posts,
            result_json=analysis.result_json if isinstance(analysis.result_json, dict) else None,
            report_created_at=analysis.created_at,
        )
        label = channel_display_ref(ch)
        msg = analysis_status_message(
            analysis_id=int(analysis.id),
            label=label,
            status=str(analysis.status),
            error_detail=analysis.error_detail,
        )
        return (
            SavedChannelAnalysisDetail(
                analysis_id=int(analysis.id),
                channel_id=int(ch.id),
                status=str(analysis.status),
                message=msg,
                created_at=analysis.created_at,
                report=report,
                channel_display_ref=label,
            ),
            None,
        )

    async def delete_channel_analysis(self, *, analysis_id: int) -> tuple[bool, str | None]:
        """Удаляет запись `analyses` по id (канал в каталоге не трогаем)."""
        res = await self._session.execute(select(Analysis).where(Analysis.id == analysis_id))
        row = res.scalar_one_or_none()
        if row is None:
            return False, "not_found"
        await self._session.delete(row)
        await self._session.commit()
        return True, None

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

        label = channel_display_ref(ch)

        res_posts = await self._session.execute(
            select(Post)
            .where(Post.channel_id == channel_id)
            .order_by(Post.posted_at.desc())
            .limit(50),
        )
        posts = list(res_posts.scalars())
        snippets: list[PostSnippet] = [
            PostSnippet(ensure_utc_aware(p.posted_at), p.text or "", views=p.views_count)
            for p in reversed(posts)
        ]

        inp = ChannelPipelineInput(
            user_intent=user_intent,
            channel_title=ch.title,
            channel_username=ch.username,
            posts=snippets,
        )
        input_refs: dict[str, Any] = {"post_count": len(snippets)}
        if user_intent.strip():
            input_refs["user_intent"] = user_intent.strip()
        analysis = Analysis(
            channel_id=ch.id,
            analyzer_id=inp.analyzer_id,
            status="running",
            input_refs_json=input_refs,
        )
        self._session.add(analysis)
        await self._session.flush()

        try:
            pipeline = ChannelAnalysisPipeline()
            result = await pipeline.run(inp)
            analysis.status = "completed"
            analysis.result_json = result.to_result_dict()
            analysis.llm_model = self._settings.openai_chat_model
        except PipelineValidationBlockedError as e:
            analysis.status = "blocked_validation"
            analysis.result_json = {"reasons": e.reasons, "validation": "block"}
            analysis.error_detail = "; ".join(e.reasons)
        except Exception as e:  # noqa: BLE001 — гранулярные коды добавятся по мере зрелости API
            analysis.status = "failed"
            analysis.error_detail = str(e)

        await self._session.commit()
        await self._session.refresh(analysis)

        msg = analysis_status_message(
            analysis_id=int(analysis.id),
            label=label,
            status=str(analysis.status),
            error_detail=analysis.error_detail,
        )

        api_status = analysis.status if analysis.status in (
            "completed",
            "blocked_validation",
            "failed",
        ) else "failed"
        report = self._build_channel_analysis_report(
            channel=ch,
            posts=posts,
            result_json=analysis.result_json if isinstance(analysis.result_json, dict) else None,
            report_created_at=analysis.created_at,
        )
        return (
            AnalyzeChannelResponse(
                analysis_id=analysis.id,
                channel_id=ch.id,
                status=api_status,
                message=msg,
                report=report,
                channel_display_ref=label,
            ),
            None,
        )

    def _normalize_channel_ref(self, channel_ref: str) -> str:
        s = channel_ref.strip()
        if s.startswith("https://t.me/"):
            s = s.replace("https://t.me/", "", 1).split("/")[0]
        elif s.startswith("http://t.me/"):
            s = s.replace("http://t.me/", "", 1).split("/")[0]
        elif s.startswith("t.me/"):
            s = s.replace("t.me/", "", 1).split("/")[0]
        return s.strip()

    def _build_channel_analysis_report(
        self,
        *,
        channel: Channel,
        posts: list[Post],
        result_json: dict[str, Any] | None,
        report_created_at: datetime | None = None,
    ) -> ChannelAnalysisReport:
        post_count = len(posts)
        avg_len = None
        if post_count:
            lengths = [len((p.text or "").strip()) for p in posts if (p.text or "").strip()]
            if lengths:
                avg_len = int(round(sum(lengths) / len(lengths)))
        freq = (
            f"{channel.posts_per_week_estimate:.2f} поста/нед"
            if channel.posts_per_week_estimate is not None
            else "Недостаточно данных"
        )
        audit = (result_json or {}).get("audit") if isinstance(result_json, dict) else None
        recs_blob = (
            (result_json or {}).get("recommendations", {}).get("items", [])
            if isinstance(result_json, dict)
            else []
        )
        strengths: list[str] = []
        risks: list[str] = []
        content_strategy = ContentStrategyReport()
        tone_of_voice = ToneOfVoiceReport()

        if isinstance(audit, dict):
            strengths = [str(x) for x in (audit.get("strengths") or [])]
            risks = [str(x) for x in (audit.get("risks") or [])]
            cs_raw = audit.get("content_strategy")
            if isinstance(cs_raw, dict):
                content_strategy = ContentStrategyReport(
                    goals=str(cs_raw.get("goals") or "").strip(),
                    main_topics=str(cs_raw.get("main_topics") or "").strip(),
                    formats=str(cs_raw.get("formats") or "").strip(),
                    cadence=str(cs_raw.get("cadence") or "").strip(),
                    rubricator=str(cs_raw.get("rubricator") or "").strip(),
                    target_audience=str(cs_raw.get("target_audience") or "").strip(),
                    seo_focus=str(cs_raw.get("seo_focus") or "").strip(),
                    engagement=str(cs_raw.get("engagement") or "").strip(),
                )
            tv_raw = audit.get("tone_of_voice")
            if isinstance(tv_raw, dict):
                tone_of_voice = ToneOfVoiceReport(
                    style=str(tv_raw.get("style") or "").strip(),
                    lexicon=str(tv_raw.get("lexicon") or "").strip(),
                    emotions=str(tv_raw.get("emotions") or "").strip(),
                    distance=str(tv_raw.get("distance") or "").strip(),
                    consistency=str(tv_raw.get("consistency") or "").strip(),
                    vs_positioning=str(tv_raw.get("vs_positioning") or "").strip(),
                )

        recommendations: list[str] = []
        if isinstance(recs_blob, list):
            for item in recs_blob[:8]:
                if not isinstance(item, dict):
                    continue
                head = str(item.get("headline") or "").strip()
                body = str(item.get("body") or "").strip()
                if head and body:
                    recommendations.append(f"{head}: {body}")
                elif head:
                    recommendations.append(head)
                elif body:
                    recommendations.append(body)

        posts_summary = (
            str((result_json or {}).get("summary") or "").strip() if isinstance(result_json, dict) else ""
        )
        if isinstance(audit, dict) and not posts_summary:
            audit_summary = str(audit.get("summary") or "").strip()
            if audit_summary:
                posts_summary = audit_summary

        if not posts_summary:
            posts_summary = "Недостаточно данных: сводка по постам не сформирована."

        return ChannelAnalysisReport(
            channel_description=(channel.description or "Описание отсутствует").strip(),
            topic=(channel.primary_topic or "Не определена").strip(),
            subscribers_count=channel.subscriber_count,
            report_created_at=report_created_at,
            publication_frequency=freq,
            avg_post_length=avg_len,
            posts_summary=posts_summary,
            content_strategy=content_strategy,
            tone_of_voice=tone_of_voice,
            strengths=strengths,
            risks=risks,
            recommendations=recommendations,
        )

    async def run_channel_analysis_by_handle(
        self,
        *,
        body: AnalyzeChannelByHandleRequest,
    ) -> AnalyzeChannelResponse:
        if self._telegram is None:
            return AnalyzeChannelResponse(
                analysis_id=0,
                channel_id=0,
                status="failed",
                message="Анализ недоступен: Telegram-сессия не подключена.",
                manual_review=ManualReviewFlags(
                    needs_review=True,
                    reason=self._telegram_live_unavailable_detail(),
                    hints=["Проверьте ссылку/username и доступность Telegram-сессии"],
                ),
            )
        channel_ref = self._normalize_channel_ref(body.channel_ref)
        try:
            info = await self._telegram.get_channel_info(channel_ref)
            recent_posts = await self._telegram.fetch_recent_posts(channel_ref, limit=body.post_limit)
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            if isinstance(exc, TelegramTelethonError):
                reason = str(exc)
            return AnalyzeChannelResponse(
                analysis_id=0,
                channel_id=0,
                status="failed",
                message="Не удалось получить данные канала.",
                manual_review=ManualReviewFlags(
                    needs_review=True,
                    reason=reason or "Канал не найден или недоступен публично",
                    hints=["Проверьте username/ссылку и повторите попытку"],
                ),
            )

        invite_slug = f"@{info.username}" if info.username else channel_ref
        ch = await self._channels.upsert_discovery_channel(
            telegram_id=info.telegram_channel_id,
            username=info.username,
            title=info.title,
            description=info.about,
            subscriber_count=info.participants_count,
            invite_slug=invite_slug,
            primary_topic=None,
            topic_search=None,
            language_hint=None,
            region_country=None,
        )
        if recent_posts:
            sorted_posts = sorted(recent_posts, key=lambda p: ensure_utc_aware(p.date_utc))
            for p in sorted_posts:
                raw = {"views": p.views, "forwards": p.forwards}
                existing_q = await self._session.execute(
                    select(Post).where(
                        Post.channel_id == ch.id,
                        Post.telegram_message_id == p.telegram_message_id,
                    )
                )
                existing = existing_q.scalar_one_or_none()
                if existing is None:
                    self._session.add(
                        Post(
                            channel_id=ch.id,
                            telegram_message_id=p.telegram_message_id,
                            posted_at=ensure_utc_aware(p.date_utc),
                            text=p.text,
                            views_count=p.views,
                            forwards_count=p.forwards,
                            raw_payload_json=raw,
                        )
                    )
                else:
                    existing.posted_at = ensure_utc_aware(p.date_utc)
                    existing.text = p.text
                    existing.views_count = p.views
                    existing.forwards_count = p.forwards
                    existing.raw_payload_json = raw
            norm_dates = [ensure_utc_aware(p.date_utc) for p in sorted_posts]
            last_dt = max(norm_dates)
            first_dt = min(norm_dates)
            ch.last_post_at = last_dt
            span_days = max((last_dt - first_dt).total_seconds() / 86400.0, 0.25)
            weeks = max(span_days / 7.0, 0.05)
            ch.posts_per_week_estimate = round(len(sorted_posts) / weeks, 3)
        ch.is_public_accessible = True
        await self._session.commit()
        result, err = await self.run_channel_analysis(
            channel_id=ch.id,
            user_intent=body.user_intent,
        )
        if err is not None or result is None:
            return AnalyzeChannelResponse(
                analysis_id=0,
                channel_id=ch.id,
                status="failed",
                message="Не удалось запустить анализ канала.",
                channel_display_ref=channel_display_ref(ch),
            )
        return result

    def _is_relevant_post_text(self, text: str) -> bool:
        t = " ".join(text.split())
        if len(t) < 30:
            return False
        lower = t.lower()
        garbage = ("joined the channel", "left the channel", "бот", "реклама", "подписывайтесь")
        return not any(x in lower for x in garbage)

    def _normalize_telethon_post(self, item: TelegramPostBrief) -> PostForAnalysis | None:
        text = (item.text or "").strip()
        if not self._is_relevant_post_text(text):
            return None
        clean = " ".join(text.split())
        urls = _URL_RE.findall(clean)
        hashtags = sorted({f"#{m.group(1).lower()}" for m in _HASHTAG_RE.finditer(clean)})
        mentions = sorted({f"@{m.group(1).lower()}" for m in _MENTION_RE.finditer(clean)})
        language = "ru" if re.search(r"[А-Яа-яЁё]", clean) else "unknown"
        return PostForAnalysis(
            message_id=int(item.telegram_message_id),
            published_at=ensure_utc_aware(item.date_utc),
            clean_text=clean,
            urls=urls[:20],
            hashtags=hashtags[:20],
            mentions=mentions[:20],
            post_type="text",
            has_media=False,
            media_type=None,
            is_forwarded=False,
            is_reply=False,
            language=language,
        )

    async def _summary_json(self, *, prompt: str) -> dict[str, Any]:
        client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=self._settings.openai_chat_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Верни только JSON. Язык ответа русский."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        usage = resp.usage
        if usage:
            logger.info(
                "scenario3 openai usage: prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    async def _build_post_summary(self, post: PostForAnalysis) -> dict[str, Any]:
        model_context_limit = 128000
        reserved_output_tokens = 900
        reserved_system_tokens = 1200
        available_input_tokens = model_context_limit - reserved_output_tokens - reserved_system_tokens
        clean_text_tokens = max(1, len(post.clean_text) // 4)
        text_for_prompt = post.clean_text
        if clean_text_tokens > int(0.5 * available_input_tokens):
            chunks = [post.clean_text[i : i + 12000] for i in range(0, len(post.clean_text), 12000)]
            text_for_prompt = "\n\n".join(chunks[:8])
        prompt = (
            "Сформируй JSON с полями: post_summary_short, post_summary_detailed, post_topics, "
            "post_keywords, post_entities, post_tone, post_search_text. "
            f"Текст поста:\n{text_for_prompt}"
        )
        data = await self._summary_json(prompt=prompt)
        return {
            "post_summary_short": str(data.get("post_summary_short") or "").strip(),
            "post_summary_detailed": str(data.get("post_summary_detailed") or "").strip(),
            "post_topics": [str(x).strip() for x in (data.get("post_topics") or []) if str(x).strip()][:12],
            "post_keywords": [str(x).strip() for x in (data.get("post_keywords") or []) if str(x).strip()][:20],
            "post_entities": [str(x).strip() for x in (data.get("post_entities") or []) if str(x).strip()][:20],
            "post_tone": str(data.get("post_tone") or "").strip(),
            "post_search_text": str(data.get("post_search_text") or "").strip() or post.clean_text,
        }

    async def _build_window_summary(self, posts_payload: list[dict[str, Any]]) -> dict[str, Any]:
        blob = "\n\n".join(
            f"[{p['message_id']}] {p['post_summary_short'] or p['clean_text'][:500]}"
            for p in posts_payload
        )
        prompt = (
            "Сформируй JSON с полями: window_summary_short, window_summary_detailed, window_topics, "
            "window_keywords, window_entities, window_tone, window_pattern_notes.\n"
            f"Материал постов:\n{blob[:40000]}"
        )
        data = await self._summary_json(prompt=prompt)
        return {
            "window_summary_short": str(data.get("window_summary_short") or "").strip(),
            "window_summary_detailed": str(data.get("window_summary_detailed") or "").strip(),
            "window_topics": [str(x).strip() for x in (data.get("window_topics") or []) if str(x).strip()][:20],
            "window_keywords": [str(x).strip() for x in (data.get("window_keywords") or []) if str(x).strip()][:30],
            "window_entities": [str(x).strip() for x in (data.get("window_entities") or []) if str(x).strip()][:30],
            "window_tone": str(data.get("window_tone") or "").strip(),
            "window_pattern_notes": str(data.get("window_pattern_notes") or "").strip(),
        }

    async def _ensure_scenario3_qdrant_schema(self, qdrant: QdrantStore, dim: int) -> None:
        post_collection = "telegram_post_summaries"
        window_collection = "telegram_channel_windows"
        await qdrant.ensure_collection_named(post_collection, dim)
        await qdrant.ensure_collection_named(window_collection, dim)
        for collection, fields in (
            (
                post_collection,
                [
                    ("entity_type", PayloadSchemaType.KEYWORD),
                    ("channel_id", PayloadSchemaType.INTEGER),
                    ("channel_username", PayloadSchemaType.KEYWORD),
                    ("message_id", PayloadSchemaType.INTEGER),
                    ("published_at", PayloadSchemaType.DATETIME),
                    ("language", PayloadSchemaType.KEYWORD),
                    ("post_type", PayloadSchemaType.KEYWORD),
                    ("has_media", PayloadSchemaType.BOOL),
                    ("is_forwarded", PayloadSchemaType.BOOL),
                ],
            ),
            (
                window_collection,
                [
                    ("entity_type", PayloadSchemaType.KEYWORD),
                    ("channel_id", PayloadSchemaType.INTEGER),
                    ("channel_username", PayloadSchemaType.KEYWORD),
                    ("analysis_window_from", PayloadSchemaType.DATETIME),
                    ("analysis_window_to", PayloadSchemaType.DATETIME),
                ],
            ),
        ):
            for field_name, field_type in fields:
                try:
                    await qdrant.ensure_payload_index(
                        collection_name=collection,
                        field_name=field_name,
                        field_type=field_type,
                    )
                except Exception:
                    logger.debug("Qdrant index exists or skipped: %s.%s", collection, field_name)

    async def summarize_recent_posts_by_handle(
        self,
        *,
        body: SummarizePostsByHandleRequest,
    ) -> SummarizePostsResponse:
        if self._telegram is None:
            raise TelegramTelethonError(self._telegram_live_unavailable_detail())
        channel_ref = self._normalize_channel_ref(body.channel_ref)
        info = await self._telegram.get_channel_info(channel_ref)
        raw_posts = await self._telegram.fetch_recent_posts(channel_ref, limit=max(80, body.post_limit * 5))
        total = len(raw_posts)
        prepared: list[PostForAnalysis] = []
        for p in raw_posts:
            norm = self._normalize_telethon_post(p)
            if norm is not None:
                prepared.append(norm)
            if len(prepared) >= body.post_limit:
                break
        # Fallback: если эвристика фильтра слишком строгая, берём непустые посты без семантической очистки мусора.
        if len(prepared) < body.post_limit:
            for p in raw_posts:
                if len(prepared) >= body.post_limit:
                    break
                txt = (p.text or "").strip()
                if not txt:
                    continue
                if any(x.message_id == int(p.telegram_message_id) for x in prepared):
                    continue
                prepared.append(
                    PostForAnalysis(
                        message_id=int(p.telegram_message_id),
                        published_at=ensure_utc_aware(p.date_utc),
                        clean_text=" ".join(txt.split()),
                        urls=_URL_RE.findall(txt)[:20],
                        hashtags=sorted({f"#{m.group(1).lower()}" for m in _HASHTAG_RE.finditer(txt)})[:20],
                        mentions=sorted({f"@{m.group(1).lower()}" for m in _MENTION_RE.finditer(txt)})[:20],
                        post_type="text",
                        has_media=False,
                        media_type=None,
                        is_forwarded=False,
                        is_reply=False,
                        language="ru" if re.search(r"[А-Яа-яЁё]", txt) else "unknown",
                    )
                )
        logger.info("scenario3 posts: fetched=%s relevant=%s requested=%s", total, len(prepared), body.post_limit)
        if not prepared:
            raise TelegramTelethonError("Нет релевантных постов для сводки в выбранном канале.")

        ch = await self._channels.upsert_discovery_channel(
            telegram_id=info.telegram_channel_id,
            username=info.username,
            title=info.title,
            description=info.about,
            subscriber_count=info.participants_count,
            invite_slug=f"@{info.username}" if info.username else channel_ref,
            primary_topic=None,
            topic_search=None,
            language_hint=None,
            region_country=None,
        )
        await self._session.commit()

        post_payloads: list[dict[str, Any]] = []
        for post in prepared:
            pdata = await self._build_post_summary(post)
            post_payloads.append({"message_id": post.message_id, "clean_text": post.clean_text, **pdata, "post": post})

        window = await self._build_window_summary(post_payloads)
        openai_client = AsyncOpenAI(api_key=self._settings.openai_api_key)
        post_collection = "telegram_post_summaries"
        window_collection = "telegram_channel_windows"
        qdrant = QdrantStore(self._settings)
        now_utc = datetime.now(timezone.utc)
        emb_model = self._settings.openai_embedding_model
        summary_model = self._settings.openai_chat_model
        version = "scenario3_v1"

        post_texts: list[str] = []
        post_ids: list[str] = []
        post_vectors_payloads: list[dict[str, Any]] = []
        for p in post_payloads:
            pf: PostForAnalysis = p["post"]
            search_text = p["post_search_text"]
            summary_text = "\n".join(x for x in (p["post_summary_short"], p["post_summary_detailed"]) if x)
            payload = {
                "entity_type": "post_summary",
                "channel_id": ch.id,
                "channel_username": (ch.username or "").strip(),
                "message_id": pf.message_id,
                "published_at": pf.published_at.isoformat(),
                "collected_at": now_utc.isoformat(),
                "post_type": pf.post_type,
                "has_media": pf.has_media,
                "media_type": pf.media_type,
                "is_forwarded": pf.is_forwarded,
                "is_reply": pf.is_reply,
                "language": pf.language,
                "clean_text": pf.clean_text,
                "post_summary_short": p["post_summary_short"],
                "post_summary_detailed": p["post_summary_detailed"],
                "post_topics": p["post_topics"],
                "post_keywords": p["post_keywords"],
                "post_entities": p["post_entities"],
                "post_tone": p["post_tone"],
                "search_text": search_text,
                "analysis_version": version,
                "embedding_model": emb_model,
                "summary_model": summary_model,
            }
            for suffix, text in (("search", search_text), ("summary", summary_text)):
                if not text.strip():
                    continue
                pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{version}|post|{ch.id}|{pf.message_id}|{suffix}"))
                post_ids.append(pid)
                post_texts.append(text)
                post_vectors_payloads.append(payload)
        qdrant_saved = False
        qdrant_error: str | None = None
        try:
            post_vectors = await openai_client.embeddings.create(model=emb_model, input=post_texts)
            dim = len(post_vectors.data[0].embedding)
            await self._ensure_scenario3_qdrant_schema(qdrant, dim)
            await qdrant.upsert_vectors_to(
                collection_name=post_collection,
                ids=post_ids,
                vectors=[x.embedding for x in post_vectors.data],
                payloads=post_vectors_payloads,
            )

            window_text = "\n".join(
                x for x in (window["window_summary_short"], window["window_summary_detailed"]) if x
            ).strip()
            window_embedding = await openai_client.embeddings.create(model=emb_model, input=[window_text])
            w_from = min(x["post"].published_at for x in post_payloads)
            w_to = max(x["post"].published_at for x in post_payloads)
            window_point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{version}|window|{ch.id}|{body.post_limit}"))
            window_payload = {
                "entity_type": "channel_window_summary",
                "channel_id": ch.id,
                "channel_username": (ch.username or "").strip(),
                "window_size": len(post_payloads),
                "source_message_ids": [int(x["message_id"]) for x in post_payloads],
                "analysis_window_from": w_from.isoformat(),
                "analysis_window_to": w_to.isoformat(),
                "window_summary_short": window["window_summary_short"],
                "window_summary_detailed": window["window_summary_detailed"],
                "window_topics": window["window_topics"],
                "window_keywords": window["window_keywords"],
                "window_entities": window["window_entities"],
                "window_tone": window["window_tone"],
                "window_pattern_notes": window["window_pattern_notes"],
                "generated_at": now_utc.isoformat(),
                "analysis_version": version,
                "embedding_model": emb_model,
                "summary_model": summary_model,
            }
            await qdrant.upsert_vectors_to(
                collection_name=window_collection,
                ids=[window_point_id],
                vectors=[window_embedding.data[0].embedding],
                payloads=[window_payload],
            )
            qdrant_saved = True
        except Exception as exc:  # noqa: BLE001
            qdrant_error = str(exc)
            logger.warning("scenario3 qdrant unavailable, skip save: %s", exc)
        finally:
            await qdrant.close()
        return SummarizePostsResponse(
            channel_id=ch.id,
            channel_display_ref=channel_display_ref(ch),
            posts_used=len(post_payloads),
            summary=window["window_summary_detailed"] or window["window_summary_short"],
            per_post_summaries=[x["post_summary_short"] for x in post_payloads if x["post_summary_short"]],
            stored_analysis_hint=(
                "Сводка по каждому посту и общее резюме сохранены в векторную базу для семантического поиска"
                if qdrant_saved
                else (
                    "Сводка построена, но не сохранена в Qdrant (проверьте QDRANT_URL/доступность сервиса). "
                    f"Причина: {qdrant_error}"
                )
            ),
        )

    async def summarize_recent_posts(
        self,
        *,
        channel_id: int,
        body: SummarizePostsRequest,
    ) -> tuple[SummarizePostsResponse, None] | tuple[None, str]:
        """Сценарий 3: сводка последних N постов через Telethon и запись в Qdrant."""
        ch = await self._channels.get_by_id(channel_id)
        if ch is None:
            return None, "not_found"
        ref = ch.username or ch.invite_slug or str(ch.telegram_id)
        result = await self.summarize_recent_posts_by_handle(
            body=SummarizePostsByHandleRequest(channel_ref=ref, post_limit=body.post_limit),
        )
        return result, None

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
