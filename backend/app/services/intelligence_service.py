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
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from statistics import mean, median
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionDeveloperMessageParam, ChatCompletionUserMessageParam
from qdrant_client.models import FieldCondition, Filter, MatchValue, PayloadSchemaType
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
    CompareChannelInsight,
    CompareChannelMetrics,
    CompareChannelsRequest,
    CompareChannelsResponse,
    ManualReviewFlags,
    SearchChannelsRequest,
    SearchChannelsResponse,
    SimilarChannelSignals,
    SimilarChannelItem,
    SimilarChannelsResponse,
    SimilarSourceChannel,
    SummarizePostsRequest,
    SummarizePostsByHandleRequest,
    SummarizePostsResponse,
    AnalyzeChannelByHandleRequest,
    SemanticResultItem,
    SemanticSearchHit,
    SemanticSearchRequest,
    SemanticSearchResponse,
    SemanticSource,
)
from app.services.channel_search_planner import merge_planner_with_user_request, plan_channel_search
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)
_URL_RE = re.compile(r"https?://\S+")
_HASHTAG_RE = re.compile(r"#([\w_]{2,64})", flags=re.UNICODE)
_MENTION_RE = re.compile(r"@([\w_]{3,64})", flags=re.UNICODE)
_DATE_LINE_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2}\]")


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
        all_topics_mode = body.search_source == "saved_catalog" and body.topic.strip().lower() in {
            "*",
            "__all__",
            "___all___",
            "all",
            "все темы",
        }
        review = self._manual_review_too_broad(body)
        if review is not None and not all_topics_mode:
            return SearchChannelsResponse(
                channels=[],
                manual_review=review,
                normalized_filters=body.model_dump(),
                background_job=None,
                has_more=False,
            )
        extra_review = await self._review_extra_conditions(body)
        if extra_review is not None and not all_topics_mode:
            return SearchChannelsResponse(
                channels=[],
                manual_review=extra_review,
                normalized_filters=body.model_dump(),
                background_job=None,
                has_more=False,
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
                    has_more=False,
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
                    has_more=False,
                )
            live_payload = body.model_dump()
            live_payload["count"] = max(1, min(15, int(body.count or 15)))
            live_payload["min_subscribers"] = None
            live_payload["max_subscribers"] = None
            username_only = (body.username_query or "").strip()
            if username_only:
                username_ref = self._normalize_channel_ref(username_only)
                topic_tokens = {t for t in re.findall(r"[\wа-яА-ЯёЁ]{3,}", body.topic.lower()) if len(t) >= 3}
                try:
                    assert self._telegram is not None
                    info = await self._telegram.get_channel_info(username_ref)
                except Exception as exc:  # noqa: BLE001
                    return SearchChannelsResponse(
                        channels=[],
                        manual_review=ManualReviewFlags(
                            needs_review=True,
                            reason=f"Канал @{username_ref.lstrip('@')} недоступен или не найден: {exc}",
                            hints=["Проверьте username и повторите поиск."],
                        ),
                        normalized_filters={**body.model_dump(mode="json"), "username_priority": True},
                        background_job=None,
                        has_more=False,
                    )
                profile_blob = f"{(info.title or '').lower()} {(info.about or '').lower()}"
                profile_tokens = {t for t in re.findall(r"[\wа-яА-ЯёЁ]{3,}", profile_blob) if len(t) >= 3}
                if topic_tokens and profile_tokens and not (topic_tokens & profile_tokens):
                    return SearchChannelsResponse(
                        channels=[],
                        manual_review=ManualReviewFlags(
                            needs_review=True,
                            reason=(
                                "Тематика найденного канала не соответствует запрошенной нише. "
                                "Уточните тему или проверьте username."
                            ),
                            hints=["Измените тему/нишу или выберите другой username."],
                        ),
                        normalized_filters={**body.model_dump(mode="json"), "username_priority": True},
                        background_job=None,
                        has_more=False,
                    )
                live_payload["username_query"] = username_ref
                live_payload["selected_channel_ids"] = []
                live_payload["live_channel_mode"] = "new"
                live_payload["channel_type"] = "all"
                live_payload["count"] = 1
                live_payload["language"] = body.language or "ru"
                live_payload["region_country"] = None
                live_payload["extra_conditions"] = None
            if body.live_channel_mode == "saved" and body.selected_channel_ids:
                live_payload["count"] = min(20, max(1, len(body.selected_channel_ids)))
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
                has_more=False,
            )

        if all_topics_mode:
            page_size = int(body.count or 20)
            catalog_limit: int | None = None if body.count is None else (page_size + 1)
            rows = await self._channels.search_catalog(
                topic="__all__",
                limit=catalog_limit,
                offset=int(body.offset or 0),
                min_subscribers=body.min_subscribers,
                max_subscribers=body.max_subscribers,
                language=body.language,
                region_country=body.region_country,
                new_only=body.channel_type == "new_only",
                sort_by=body.sort_by,
                sort_order=body.sort_order,
                username_query=body.username_query,
                last_post_at_gte=last_post_at_gte,
                last_post_at_lte=last_post_at_lte,
            )
            has_more = False
            if page_size > 0 and len(rows) > page_size:
                has_more = True
                rows = rows[:page_size]
            cards = [ChannelCard.model_validate(r) for r in rows]
            normalized = {
                **body.model_dump(mode="json"),
                "all_topics_mode": True,
                "saved_catalog_topics_tried": ["__all__"],
            }
            return SearchChannelsResponse(
                channels=cards,
                manual_review=None,
                normalized_filters=normalized,
                background_job=None,
                has_more=has_more,
            )

        planner = await plan_channel_search(self._settings, body.model_dump(mode="json"))
        merged = merge_planner_with_user_request(body.model_dump(mode="json"), planner)
        planner_topic = str(merged.get("search_topic") or body.topic).strip()
        user_topic = body.topic.strip()
        # Для серверной пагинации размер страницы должен задаваться клиентом,
        # иначе planner может "сжимать" count (например до 17) и ломать infinite scroll.
        page_size = int(body.count or merged.get("count") or 20)
        catalog_limit: int | None = None if body.count is None else (page_size + 1)
        eff_sort_by = "last_sync_at" if merged.get("channel_type") == "new_only" else body.sort_by
        eff_sort_order = "desc" if merged.get("channel_type") == "new_only" else body.sort_order
        catalog_kw: dict[str, Any] = {
            "limit": catalog_limit,
            "offset": int(body.offset or 0),
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
        has_more = False
        if page_size > 0 and len(rows) > page_size:
            has_more = True
            rows = rows[:page_size]
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
            has_more=has_more,
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
        post_limit: int = 10,
    ) -> tuple[AnalyzeChannelResponse, None] | tuple[None, str]:
        """
        Сценарий 2: AI-анализ канала, результат в `Analysis`.

        Возвращает либо (response, None), либо (None, error_code) если канал не найден.
        """
        ch = await self._channels.get_by_id(channel_id)
        if ch is None:
            return None, "not_found"

        label = channel_display_ref(ch)

        target_posts = max(3, int(post_limit))
        sample_limit = max(80, target_posts * 8)
        res_posts = await self._session.execute(
            select(Post)
            .where(Post.channel_id == channel_id)
            .order_by(Post.posted_at.desc())
            .limit(sample_limit),
        )
        posts = list(res_posts.scalars())
        if len(posts) == 0 and self._telegram is not None:
            channel_ref = (ch.username or ch.invite_slug or str(ch.telegram_id or "")).strip()
            try:
                recent_posts = await self._telegram.fetch_recent_posts(channel_ref, limit=max(40, target_posts * 5))
            except TelegramTelethonError:
                recent_posts = []
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
                await self._session.commit()
                res_posts = await self._session.execute(
                    select(Post)
                    .where(Post.channel_id == channel_id)
                    .order_by(Post.posted_at.desc())
                    .limit(sample_limit),
                )
                posts = list(res_posts.scalars())
        filtered_posts, snippets = self._prepare_db_posts_for_analysis(posts, target_count=target_posts)

        inp = ChannelPipelineInput(
            user_intent=user_intent,
            channel_title=ch.title,
            channel_username=ch.username,
            posts=snippets,
        )
        input_refs: dict[str, Any] = {"post_count": len(snippets), "raw_post_count": len(posts)}
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
            posts=filtered_posts,
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
        else:
            posts_summary = self._compress_posts_summary(posts_summary)

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
            recent_posts = await self._telegram.fetch_recent_posts(channel_ref, limit=max(80, body.post_limit * 5))
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
            post_limit=body.post_limit,
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

    def _post_to_snippet(self, post: Post) -> PostSnippet | None:
        text = " ".join((post.text or "").split())
        if not text:
            return None
        return PostSnippet(ensure_utc_aware(post.posted_at), text, views=post.views_count)

    def _prepare_db_posts_for_analysis(
        self,
        posts: list[Post],
        *,
        target_count: int,
    ) -> tuple[list[Post], list[PostSnippet]]:
        strict_pairs: list[tuple[Post, PostSnippet]] = []
        fallback_pairs: list[tuple[Post, PostSnippet]] = []
        for p in posts:
            snippet = self._post_to_snippet(p)
            if snippet is None:
                continue
            if self._is_relevant_post_text(snippet.text):
                strict_pairs.append((p, snippet))
            else:
                fallback_pairs.append((p, snippet))
            if len(strict_pairs) >= target_count:
                break

        selected_pairs = strict_pairs[:target_count]
        if len(selected_pairs) < target_count:
            selected_ids = {int(p.id) for p, _ in selected_pairs if getattr(p, "id", None) is not None}
            for p, s in fallback_pairs:
                pid = int(p.id) if getattr(p, "id", None) is not None else None
                if pid is not None and pid in selected_ids:
                    continue
                selected_pairs.append((p, s))
                if len(selected_pairs) >= target_count:
                    break

        selected_pairs = list(reversed(selected_pairs))
        return [p for p, _ in selected_pairs], [s for _, s in selected_pairs]

    def _compress_posts_summary(self, text: str, *, max_len: int = 900, max_lines: int = 8) -> str:
        src = str(text or "").strip()
        if not src:
            return src
        lines = [" ".join(x.split()) for x in src.splitlines()]
        filtered = [x for x in lines if x and not _DATE_LINE_RE.match(x)]
        if not filtered:
            filtered = [x for x in lines if x]
        brief = "\n".join(filtered[:max_lines]).strip()
        if len(brief) > max_len:
            brief = brief[: max_len - 1].rstrip() + "…"
        return brief or src[:max_len]

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
        saved_post_points = 0
        saved_window_points = 0
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
            saved_post_points = len(post_ids)

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
            saved_window_points = 1
            qdrant_saved = True
            logger.info(
                "scenario3 qdrant saved: channel_id=%s post_points=%s window_points=%s collections=%s,%s",
                ch.id,
                saved_post_points,
                saved_window_points,
                post_collection,
                window_collection,
            )
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

    def _semantic_route_mode(self, query: str) -> tuple[str | None, str | None]:
        q = query.strip().lower()
        if len(q) < 8:
            return None, "Слишком общий запрос"
        vague = {"найди интересное", "что сейчас важно", "найди хорошие каналы", "найди про"}
        if q in vague:
            return None, "Слишком общий запрос"
        personal_chat_markers = (
            "думаешь ты",
            "что думаешь",
            "как думаешь",
            "ты думаешь",
            "твое мнение",
            "твоё мнение",
            "расскажи о себе",
            "кто ты",
        )
        if any(marker in q for marker in personal_chat_markers):
            return None, "Запрос не относится к анализу накопленных постов/каналов"
        has_channels = any(x in q for x in ("канал", "каналы"))
        has_posts = any(x in q for x in ("пост", "посты", "сообщения"))
        has_question = any(q.startswith(x) for x in ("о чем", "что", "какие", "есть ли", "почему", "зачем"))
        has_corpus_anchor = any(
            x in q
            for x in (
                "канал",
                "каналы",
                "пост",
                "посты",
                "сообщени",
                "в накопленных",
                "в данных",
                "по данным",
                "по постам",
                "про ",
            )
        )
        if has_channels and not has_posts:
            return "channel_search", None
        if has_posts and not has_channels:
            return "post_search", None
        if has_question:
            if not has_corpus_anchor:
                return None, "Неясно, что искать в накопленных постах или каналах"
            return "question_answering_over_posts", None
        if has_channels and has_posts:
            return None, "Неясно, нужно искать посты или каналы"
        if "про " not in q and "о " not in q:
            return None, "Не указана тема анализа"
        return "post_search", None

    async def semantic_search_scenario4(self, body: SemanticSearchRequest) -> SemanticSearchResponse:
        logger.info("scenario4 routing: raw_query=%s", body.query)
        mode, reason = self._semantic_route_mode(body.query)
        if reason:
            return SemanticSearchResponse(needs_review=True, reason=reason, query=body.query, mode=None)

        openai = AsyncOpenAI(api_key=self._settings.openai_api_key)
        emb = await openai.embeddings.create(model=self._settings.openai_embedding_model, input=[body.query])
        qvec = emb.data[0].embedding
        logger.info("scenario4 retrieval: mode=%s limit=%s", mode, body.limit)
        qdrant = QdrantStore(self._settings)
        try:
            has_post_collection = await qdrant.collection_exists("telegram_post_summaries")
            has_window_collection = await qdrant.collection_exists("telegram_channel_windows")
            post_points_count = (
                await qdrant.collection_points_count("telegram_post_summaries")
                if has_post_collection
                else None
            )
            window_points_count = (
                await qdrant.collection_points_count("telegram_channel_windows")
                if has_window_collection
                else None
            )
            logger.info(
                "scenario4 collections: post=%s (%s points) window=%s (%s points) qdrant_url=%s",
                has_post_collection,
                post_points_count,
                has_window_collection,
                window_points_count,
                self._settings.qdrant_url,
            )
            if not has_post_collection or not has_window_collection:
                missing = []
                if not has_post_collection:
                    missing.append("telegram_post_summaries")
                if not has_window_collection:
                    missing.append("telegram_channel_windows")
                return SemanticSearchResponse(
                    needs_review=True,
                    reason=(
                        "В векторной базе пока нет нужных коллекций: "
                        + ", ".join(missing)
                        + ". Сначала запустите «Резюмировать посты» минимум для одного канала."
                    ),
                    query=body.query,
                    mode=mode,
                )
            if (post_points_count or 0) <= 0 and (window_points_count or 0) <= 0:
                return SemanticSearchResponse(
                    needs_review=True,
                    reason=(
                        "Коллекции в векторной базе существуют, но пока пустые. "
                        "Запустите «Резюмировать посты» и убедитесь в сообщении об успешном сохранении в векторную базу."
                    ),
                    query=body.query,
                    mode=mode,
                )
            post_points = await qdrant.search_in_collection(
                collection_name="telegram_post_summaries",
                query_vector=qvec,
                limit=max(30, body.limit * 3),
            )
            window_points = await qdrant.search_in_collection(
                collection_name="telegram_channel_windows",
                query_vector=qvec,
                limit=max(20, body.limit * 2),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("scenario4 retrieval failed: %s", exc)
            return SemanticSearchResponse(
                needs_review=True,
                reason=(
                    "Не удалось выполнить поиск в векторной базе. "
                    "Проверьте доступность Qdrant и наличие данных из сценария 3. "
                    f"Техническая причина: {exc}"
                ),
                query=body.query,
                mode=mode,
            )
        finally:
            await qdrant.close()

        username_filter = (body.channel_username or "").strip().lstrip("@").lower()
        post_rows: list[dict[str, Any]] = []
        for p in post_points:
            payload = dict(p.payload or {})
            uname = str(payload.get("channel_username") or "").lstrip("@").lower()
            if username_filter and uname != username_filter:
                continue
            txt = str(payload.get("post_summary_short") or payload.get("search_text") or payload.get("clean_text") or "")
            bonus = 0.08 if any(w in txt.lower() for w in body.query.lower().split()[:4]) else 0.0
            score = float(p.score or 0.0) + bonus
            source_url = None
            if payload.get("channel_username") and payload.get("message_id"):
                source_url = f"https://t.me/{str(payload['channel_username']).lstrip('@')}/{int(payload['message_id'])}"
            post_rows.append(
                {
                    "score": score,
                    "channel_username": payload.get("channel_username"),
                    "message_id": payload.get("message_id"),
                    "summary": txt,
                    "source_url": source_url,
                    "payload": payload,
                    "point_id": str(p.id),
                }
            )
        post_rows.sort(key=lambda x: x["score"], reverse=True)

        window_rows: list[dict[str, Any]] = []
        for p in window_points:
            payload = dict(p.payload or {})
            uname = str(payload.get("channel_username") or "").lstrip("@").lower()
            if username_filter and uname != username_filter:
                continue
            txt = str(payload.get("window_summary_short") or payload.get("window_summary_detailed") or "")
            window_rows.append(
                {
                    "score": float(p.score or 0.0),
                    "channel_username": payload.get("channel_username"),
                    "summary": txt,
                    "payload": payload,
                    "point_id": str(p.id),
                }
            )
        window_rows.sort(key=lambda x: x["score"], reverse=True)

        hits: list[SemanticSearchHit] = []
        for row in post_rows[: body.limit]:
            p = row["payload"]
            hits.append(
                SemanticSearchHit(
                    point_id=row["point_id"],
                    score=row["score"],
                    channel_id=int(p["channel_id"]) if p.get("channel_id") is not None else None,
                    channel_username=str(p.get("channel_username") or "").strip() or None,
                    post_id=int(p["message_id"]) if p.get("message_id") is not None else None,
                    published_at=(
                        datetime.fromisoformat(str(p["published_at"]))
                        if p.get("published_at")
                        else None
                    ),
                    source_url=row["source_url"],
                    content_type="post",
                    text_preview=(row["summary"][:400] + "…") if len(row["summary"]) > 400 else row["summary"],
                )
            )

        sources = [
            SemanticSource(
                channel_username=r.get("channel_username"),
                message_id=int(r["message_id"]) if r.get("message_id") is not None else None,
                source_url=r.get("source_url"),
                score=r.get("score"),
                summary=r.get("summary"),
            )
            for r in post_rows[: body.limit]
        ]

        results: list[SemanticResultItem] = []
        if mode == "post_search":
            for r in post_rows[: body.limit]:
                results.append(
                    SemanticResultItem(
                        channel_username=r.get("channel_username"),
                        title="Релевантный пост",
                        relevance_reason="Семантически близок к запросу по теме и формулировкам.",
                        source_url=r.get("source_url"),
                        score=r.get("score"),
                    )
                )
            answer = "Найдены наиболее релевантные посты по вашему запросу."
        elif mode == "channel_search":
            by_channel: dict[str, dict[str, Any]] = {}
            for r in post_rows[: max(body.limit * 3, 10)]:
                key = str(r.get("channel_username") or "")
                if not key:
                    continue
                entry = by_channel.setdefault(
                    key,
                    {
                        "sum_score": 0.0,
                        "count": 0,
                        "source_url": f"https://t.me/{key.lstrip('@')}",
                    },
                )
                entry["sum_score"] += float(r.get("score") or 0.0)
                entry["count"] += 1
            ranked = sorted(
                by_channel.items(),
                key=lambda x: (x[1]["sum_score"] / max(1, x[1]["count"])),
                reverse=True,
            )[: body.limit]
            for uname, data in ranked:
                avg_score = float(data["sum_score"]) / max(1, int(data["count"]))
                results.append(
                    SemanticResultItem(
                        channel_username=uname,
                        title=f"Канал @{str(uname).lstrip('@')}",
                        relevance_reason=None,
                        source_url=data.get("source_url"),
                        score=avg_score,
                    )
                )
            answer = "Найдены каналы, которые чаще всего пишут по нужной теме."
        else:
            evidence = "\n".join(f"- @{s.channel_username}: {s.summary}" for s in sources[:8] if s.summary)
            prompt = (
                "Дай короткий ответ на вопрос строго по evidence. Не выдумывай факты.\n"
                f"Вопрос: {body.query}\nEvidence:\n{evidence[:6000]}"
            )
            try:
                comp = await openai.chat.completions.create(
                    model=self._settings.openai_chat_model,
                    messages=[
                        {"role": "system", "content": "Ты аналитик. Отвечай только по данным evidence."},
                        {"role": "user", "content": prompt},
                    ],
                )
                answer = (comp.choices[0].message.content or "").strip() or "Недостаточно evidence для уверенного ответа."
            except Exception:
                answer = "Недостаточно evidence для уверенного ответа."
            for s in sources[: body.limit]:
                results.append(
                    SemanticResultItem(
                        channel_username=s.channel_username,
                        title="Источник для ответа",
                        relevance_reason="Использован как evidence для ответа на вопрос.",
                        source_url=s.source_url,
                        score=s.score,
                    )
                )

        logger.info("scenario4 complete: mode=%s results=%s sources=%s", mode, len(results), len(sources))
        return SemanticSearchResponse(
            needs_review=False,
            reason=None,
            query=body.query,
            mode=mode,
            answer=answer,
            results=results,
            sources=sources,
            hits=hits,
            synthesis_placeholder=window_rows[0]["summary"] if window_rows and mode != "question_answering_over_posts" else None,
        )

    async def compare_channels(
        self,
        body: CompareChannelsRequest,
    ) -> CompareChannelsResponse | None:
        """Сценарий 5: сравнение каналов за 30 дней (метрики + evidence + AI synthesis)."""

        def percentile(vals: list[float], p: float) -> float:
            if not vals:
                return 0.0
            arr = sorted(vals)
            if len(arr) == 1:
                return float(arr[0])
            idx = (len(arr) - 1) * p
            lo = int(idx)
            hi = min(lo + 1, len(arr) - 1)
            frac = idx - lo
            return float(arr[lo] * (1 - frac) + arr[hi] * frac)

        now_utc = datetime.now(timezone.utc)
        from_dt = now_utc - timedelta(days=30)
        rows_out: list[CompareChannelRow] = []
        raw_metrics: list[dict[str, Any]] = []
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
                )
            )

            posts_window: list[TelegramPostBrief] = []
            if self._telegram is not None:
                ident: str | int = ch.username if ch.username else ch.telegram_id
                try:
                    fetched = await self._telegram.fetch_recent_posts(ident, limit=100)
                    posts_window = [p for p in fetched if ensure_utc_aware(p.date_utc) >= from_dt and (p.text or "").strip()]
                except Exception as exc:  # noqa: BLE001
                    logger.warning("compare.telethon fetch failed channel_id=%s: %s", ch.id, exc)

            if not posts_window:
                db_posts_q = await self._session.execute(
                    select(Post)
                    .where(Post.channel_id == ch.id)
                    .where(Post.posted_at >= from_dt)
                    .order_by(Post.posted_at.desc())
                    .limit(120)
                )
                db_posts = list(db_posts_q.scalars().all())
                posts_window = [
                    TelegramPostBrief(
                        telegram_message_id=int(p.telegram_message_id),
                        date_utc=ensure_utc_aware(p.posted_at),
                        text=p.text,
                        views=p.views_count,
                        forwards=p.forwards_count,
                    )
                    for p in db_posts
                    if (p.text or "").strip()
                ]

            views = [float(p.views or 0) for p in posts_window if (p.views or 0) > 0]
            fwds = [float(p.forwards or 0) for p in posts_window]
            ers = [float((p.forwards or 0) / max((p.views or 0), 1)) for p in posts_window if (p.views or 0) > 0]

            by_week: dict[str, int] = {}
            by_day_avg_views: dict[str, list[float]] = {}
            for p in posts_window:
                dt = ensure_utc_aware(p.date_utc)
                year_week = f"{dt.isocalendar().year}-{dt.isocalendar().week}"
                by_week[year_week] = by_week.get(year_week, 0) + 1
                day = dt.date().isoformat()
                by_day_avg_views.setdefault(day, []).append(float(p.views or 0))

            weekly_counts = list(by_week.values())
            weekly_mean = mean(weekly_counts) if weekly_counts else 0.0
            weekly_cv = (float((sum((x - weekly_mean) ** 2 for x in weekly_counts) / max(len(weekly_counts), 1)) ** 0.5) / max(weekly_mean, 1e-6)) if weekly_counts else 1.0
            weekly_stability = max(0.0, min(100.0, 100.0 * (1.0 - min(1.0, weekly_cv))))

            day_series = sorted((d, mean(v)) for d, v in by_day_avg_views.items())
            if len(day_series) >= 2:
                xs = list(range(len(day_series)))
                ys = [float(v) for _, v in day_series]
                mx = mean(xs)
                my = mean(ys)
                num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
                den = sum((x - mx) ** 2 for x in xs) or 1.0
                trend_slope = num / den
            else:
                trend_slope = 0.0

            all_text = " ".join((p.text or "") for p in posts_window).lower()
            tone_label = "нет данных" if not posts_window else "нейтральный"
            if posts_window and any(w in all_text for w in ("кризис", "падение", "риск", "проблем")):
                tone_label = "тревожный"
            elif posts_window and any(w in all_text for w in ("рост", "успех", "возможност", "прибыль")):
                tone_label = "позитивный"
            topic_labels: list[str] = []
            for t in ("финанс", "инвест", "крипт", "недвиж", "ai", "маркетинг", "стартап"):
                if t in all_text:
                    topic_labels.append(t)
            if not topic_labels:
                topic_labels = [ch.primary_topic or "общая тематика"]

            commercial_markers = ("подписывайтесь", "реклама", "партнер", "партнёр", "скидк", "купит", "промокод")
            commercial_posts = sum(1 for p in posts_window if any(m in (p.text or "").lower() for m in commercial_markers))
            commercial_share = commercial_posts / max(len(posts_window), 1)

            first_dt = min((ensure_utc_aware(p.date_utc) for p in posts_window), default=from_dt)
            last_dt = max((ensure_utc_aware(p.date_utc) for p in posts_window), default=now_utc)
            span_days = max((last_dt - first_dt).total_seconds() / 86400.0, 1.0)
            freq_week = len(posts_window) / (span_days / 7.0)
            avg_views = float(mean(views)) if views else 0.0
            med_views = float(median(views)) if views else 0.0
            p75_views = percentile(views, 0.75)
            avg_fwds = float(mean(fwds)) if fwds else 0.0
            er_mean = float(mean(ers)) if ers else 0.0
            er_p75 = percentile(ers, 0.75)

            evidence_urls: list[str] = []
            for p in sorted(posts_window, key=lambda x: (x.forwards or 0, x.views or 0), reverse=True)[:5]:
                if ch.username:
                    evidence_urls.append(f"https://t.me/{ch.username.lstrip('@')}/{p.telegram_message_id}")

            raw_metrics.append(
                {
                    "channel": ch,
                    "posts_in_window": len(posts_window),
                    "posting_frequency_per_week": freq_week,
                    "avg_views": avg_views,
                    "median_views": med_views,
                    "p75_views": p75_views,
                    "avg_forwards": avg_fwds,
                    "er_forward_rate_mean": er_mean,
                    "er_forward_rate_p75": er_p75,
                    "weekly_stability_score": weekly_stability,
                    "views_trend_slope": trend_slope,
                    "tone_label": tone_label,
                    "topic_labels": topic_labels[:6],
                    "commercial_intent_share": commercial_share,
                    "evidence_urls": evidence_urls,
                }
            )

        max_avg_views = max((m["avg_views"] for m in raw_metrics), default=1.0)
        max_freq = max((m["posting_frequency_per_week"] for m in raw_metrics), default=1.0)
        max_er = max((m["er_forward_rate_mean"] for m in raw_metrics), default=1.0)
        max_stability = 100.0
        max_trend = max((abs(m["views_trend_slope"]) for m in raw_metrics), default=1.0)
        insights: list[CompareChannelInsight] = []
        for m in raw_metrics:
            score = (
                0.24 * (m["avg_views"] / max(max_avg_views, 1e-6))
                + 0.18 * (m["posting_frequency_per_week"] / max(max_freq, 1e-6))
                + 0.22 * (m["er_forward_rate_mean"] / max(max_er, 1e-6))
                + 0.16 * (m["weekly_stability_score"] / max_stability)
                + 0.10 * (0.5 + 0.5 * (m["views_trend_slope"] / max(max_trend, 1e-6)))
                + 0.10 * (1.0 - min(1.0, m["commercial_intent_share"]))
            ) * 100.0
            ch = m["channel"]
            strengths: list[str] = []
            if m["posts_in_window"] == 0:
                strengths.append("За последние 30 дней в доступных данных не найдено постов для сравнения.")
            if m["er_forward_rate_mean"] >= 0.03:
                strengths.append("Выше среднего уровень пересылок к просмотрам (прокси вовлечённости).")
            if m["weekly_stability_score"] >= 65:
                strengths.append("Стабильный ритм публикаций в 30-дневном окне.")
            if m["views_trend_slope"] > 0:
                strengths.append("Есть положительный тренд охватов по дням.")
            if not strengths:
                strengths.append("Канал регулярно публикует контент и имеет измеримый охват.")

            recommendations: list[str] = []
            if m["posts_in_window"] == 0:
                recommendations.append("Проверьте доступ к постам канала в Telethon и актуальность локальной истории постов.")
            if m["commercial_intent_share"] > 0.35:
                recommendations.append("Снизить долю продающих постов и усилить контент экспертного типа.")
            if m["weekly_stability_score"] < 45:
                recommendations.append("Выровнять публикационный график для повышения предсказуемости охватов.")
            if m["er_forward_rate_mean"] < 0.01:
                recommendations.append("Добавить больше цитируемого и прикладного контента для роста пересылок.")
            if not recommendations:
                recommendations.append("Поддерживать текущий формат, усиливая темы с максимальным откликом.")

            metrics = CompareChannelMetrics(
                posts_in_window=m["posts_in_window"],
                posting_frequency_per_week=round(m["posting_frequency_per_week"], 3),
                avg_views=round(m["avg_views"], 2),
                median_views=round(m["median_views"], 2),
                p75_views=round(m["p75_views"], 2),
                avg_forwards=round(m["avg_forwards"], 2),
                er_forward_rate_mean=round(m["er_forward_rate_mean"], 4),
                er_forward_rate_p75=round(m["er_forward_rate_p75"], 4),
                weekly_stability_score=round(m["weekly_stability_score"], 2),
                views_trend_slope=round(m["views_trend_slope"], 3),
                tone_label=m["tone_label"],
                topic_labels=m["topic_labels"],
                commercial_intent_share=round(m["commercial_intent_share"], 4),
                normalized_score=round(max(0.0, min(100.0, score)), 2),
            )
            insights.append(
                CompareChannelInsight(
                    channel_id=ch.id,
                    username=ch.username,
                    strengths=strengths,
                    recommendations=recommendations,
                    evidence_urls=m["evidence_urls"],
                    metrics=metrics,
                )
            )

        insights.sort(key=lambda i: i.metrics.normalized_score, reverse=True)
        notes = (
            "Сравнение выполнено по окну 30 дней на основе охватов, пересылок, стабильности публикаций, "
            "тренда просмотров и контентных признаков. Нормализованный рейтинг учитывает размер и качество динамики."
        )
        if self._settings.openai_api_key:
            try:
                openai = AsyncOpenAI(api_key=self._settings.openai_api_key)
                compact = [
                    {
                        "channel": x.username or str(x.channel_id),
                        "score": x.metrics.normalized_score,
                        "er": x.metrics.er_forward_rate_mean,
                        "freq": x.metrics.posting_frequency_per_week,
                        "stability": x.metrics.weekly_stability_score,
                        "tone": x.metrics.tone_label,
                        "topics": x.metrics.topic_labels,
                    }
                    for x in insights
                ]
                prompt = (
                    "Сделай сравнительный анализ каналов на русском, кратко и по фактам. "
                    "Структура: 1) кто лидирует и почему; 2) сильные стороны каждого; 3) практические рекомендации. "
                    "Не используй английские слова, если есть русский эквивалент. "
                    f"Данные: {json.dumps(compact, ensure_ascii=False)}"
                )
                comp = await openai.chat.completions.create(
                    model=self._settings.openai_chat_model,
                    messages=[
                        {"role": "system", "content": "Ты аналитик Telegram-каналов. Не выдумывай факты."},
                        {"role": "user", "content": prompt},
                    ],
                )
                notes = (comp.choices[0].message.content or "").strip() or notes
            except Exception as exc:  # noqa: BLE001
                logger.warning("compare llm synthesis failed: %s", exc)

        return CompareChannelsResponse(
            rows=rows_out,
            comparison_notes=notes,
            comparison_window_days=30,
            generated_at=now_utc,
            insights=insights,
        )

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
        limit: int = 5,
    ) -> tuple[SimilarChannelsResponse, None] | tuple[None, str]:
        """Сценарий 6: похожие каналы — Qdrant (сводки/окна/профиль) + fallback по каталогу."""
        del vector
        _PROFILE_COLL = "telegram_channel_profiles"

        def _norm_topic_tokens(*parts: str | None) -> set[str]:
            raw = " ".join(str(p).lower() for p in parts if p)
            return {t for t in re.findall(r"[\wа-яА-ЯёЁ]{3,}", raw) if len(t) >= 3}

        def _topics_from_row(row: Channel) -> set[str]:
            out: set[str] = set()
            if row.primary_topic:
                for part in str(row.primary_topic).replace(";", ",").split(","):
                    t = part.strip().lower()
                    if len(t) >= 3:
                        out.add(t)
            tj = row.topics_json
            if isinstance(tj, list):
                for x in tj:
                    s = str(x).strip().lower()
                    if len(s) >= 2:
                        out.add(s)
            return out

        def _to_vec(raw: Any) -> list[float]:
            if isinstance(raw, dict):
                if not raw:
                    return []
                raw = next(iter(raw.values()))
            if not raw:
                return []
            return [float(x) for x in raw]

        def _avg_vector(vectors: list[list[float]]) -> list[float]:
            if not vectors:
                return []
            dim = len(vectors[0])
            acc = [0.0] * dim
            for v in vectors:
                if len(v) != dim:
                    continue
                for i in range(dim):
                    acc[i] += v[i]
            n = max(1, len([x for x in vectors if len(x) == dim]))
            return [x / n for x in acc]

        def _jaccard(a: set[str], b: set[str]) -> float:
            if not a or not b:
                return 0.0
            inter = len(a & b)
            union = len(a | b)
            return float(inter) / float(union) if union else 0.0

        def _top_overlap_tokens(a: set[str], b: set[str], cap: int = 3) -> list[str]:
            shared = sorted((a & b), key=lambda x: (-len(x), x))
            return shared[:cap]

        def _freq_sim(a: float | None, b: float | None) -> float:
            x = float(a or 0.0)
            y = float(b or 0.0)
            denom = max(x, y, 1.0)
            return max(0.0, 1.0 - abs(x - y) / denom)

        async def _embed_query_text(text: str) -> list[float]:
            if not self._settings.openai_api_key or not text.strip():
                return []
            openai = AsyncOpenAI(api_key=self._settings.openai_api_key)
            emb = await openai.embeddings.create(
                model=self._settings.openai_embedding_model,
                input=[text[: self._settings.embedding_max_chunk_chars]],
            )
            return list(emb.data[0].embedding)

        ch = await self._channels.get_by_id(seed_channel_id)
        if ch is None:
            return None, "not_found"
        logger.info("similar.validation seed_channel_id=%s", seed_channel_id)
        quality_notes: list[str] = []

        exclude_other = Filter(
            must_not=[
                FieldCondition(key="channel_id", match=MatchValue(value=int(seed_channel_id))),
            ],
        )

        qdrant = QdrantStore(self._settings)
        try:
            has_posts = await qdrant.collection_exists("telegram_post_summaries")
            has_windows = await qdrant.collection_exists("telegram_channel_windows")
            has_profile = await qdrant.collection_exists(_PROFILE_COLL)
            if not has_posts and not has_windows and not has_profile:
                quality_notes.append(
                    "Векторные коллекции недоступны — используется подбор только по карточкам каналов в каталоге."
                )

            seed_posts: list[Any] = []
            seed_windows: list[Any] = []
            if has_posts:
                seed_posts = await qdrant.scroll_in_collection(
                    collection_name="telegram_post_summaries",
                    limit=80,
                    query_filter=Filter(
                        must=[FieldCondition(key="channel_id", match=MatchValue(value=int(ch.id)))]
                    ),
                    with_vectors=True,
                )
            if has_windows:
                seed_windows = await qdrant.scroll_in_collection(
                    collection_name="telegram_channel_windows",
                    limit=10,
                    query_filter=Filter(
                        must=[FieldCondition(key="channel_id", match=MatchValue(value=int(ch.id)))]
                    ),
                    with_vectors=True,
                )
            seed_profile_pts: list[Any] = []
            if has_profile:
                seed_profile_pts = await qdrant.scroll_in_collection(
                    collection_name=_PROFILE_COLL,
                    limit=5,
                    query_filter=Filter(
                        must=[FieldCondition(key="channel_id", match=MatchValue(value=int(ch.id)))]
                    ),
                    with_vectors=True,
                )

            logger.info(
                "similar.profile_building seed_channel_id=%s posts=%s windows=%s profiles=%s",
                ch.id,
                len(seed_posts),
                len(seed_windows),
                len(seed_profile_pts),
            )

            seed_topics: set[str] = set()
            seed_tones: set[str] = set()
            seed_vectors: list[list[float]] = []
            for p in list(seed_posts) + list(seed_windows):
                payload = dict(p.payload or {})
                for t in payload.get("post_topics") or payload.get("window_topics") or []:
                    tt = str(t).strip().lower()
                    if tt:
                        seed_topics.add(tt)
                tone = str(payload.get("tone_label") or payload.get("window_tone") or "").strip().lower()
                if tone:
                    seed_tones.add(tone)
                vec = _to_vec(getattr(p, "vector", None))
                if vec:
                    seed_vectors.append(vec)
            for p in seed_profile_pts:
                vec = _to_vec(getattr(p, "vector", None))
                if vec:
                    seed_vectors.append(vec)

            if len(seed_posts) < 2 and len(seed_windows) < 1:
                quality_notes.append(
                    "Мало сводок постов по исходному каналу в Qdrant — точность ниже; "
                    "для лучшего матча выполните «Резюмировать посты» для этого канала."
                )

            query_vec = _avg_vector(seed_vectors)
            if not query_vec:
                catalog_blob = "\n".join(
                    str(x).strip()
                    for x in (ch.title, ch.description, ch.primary_topic, ch.topic_search)
                    if x and str(x).strip()
                )
                if self._settings.openai_api_key and catalog_blob.strip():
                    query_vec = await _embed_query_text(catalog_blob)
                    quality_notes.append(
                        "Запрос близости построен по метаданным канала (название, описание, тема), "
                        "так как в Qdrant не найдены векторы сводок."
                    )
                if not query_vec:
                    return (
                        SimilarChannelsResponse(
                            needs_review=True,
                            reason=(
                                "Недостаточно данных для подбора: нет векторного профиля и не настроены ключи "
                                "OpenAI для расчёта эмбеддинга по карточке канала."
                            ),
                            mode=None,
                            source_channel=SimilarSourceChannel(channel_id=ch.id, channel_username=ch.username),
                            results=[],
                            quality_notes=quality_notes,
                        ),
                        None,
                    )

            logger.info("similar.retrieval seed_channel_id=%s", ch.id)
            pool_size = max(60, limit * 12)
            cand_points: list[Any] = []
            if has_posts:
                cand_points.extend(
                    await qdrant.search_in_collection(
                        collection_name="telegram_post_summaries",
                        query_vector=query_vec,
                        limit=pool_size,
                        query_filter=exclude_other,
                    )
                )
            if has_windows:
                cand_points.extend(
                    await qdrant.search_in_collection(
                        collection_name="telegram_channel_windows",
                        query_vector=query_vec,
                        limit=max(24, limit * 5),
                        query_filter=exclude_other,
                    )
                )
            if has_profile:
                cand_points.extend(
                    await qdrant.search_in_collection(
                        collection_name=_PROFILE_COLL,
                        query_vector=query_vec,
                        limit=max(40, limit * 8),
                        query_filter=exclude_other,
                    )
                )

            cand_by_channel: dict[int, dict[str, Any]] = {}
            for p in cand_points:
                payload = dict(p.payload or {})
                cid_raw = payload.get("channel_id")
                if cid_raw is None:
                    continue
                cid = int(cid_raw)
                if cid <= 0 or cid == seed_channel_id:
                    continue
                e = cand_by_channel.setdefault(
                    cid,
                    {
                        "scores": [],
                        "topics": set(),
                        "tones": set(),
                        "catalog_only": False,
                    },
                )
                e["scores"].append(float(p.score or 0.0))
                for t in payload.get("post_topics") or payload.get("window_topics") or []:
                    tt = str(t).strip().lower()
                    if tt:
                        e["topics"].add(tt)
                tone = str(payload.get("tone_label") or payload.get("window_tone") or "").strip().lower()
                if tone:
                    e["tones"].add(tone)

            seed_text_tokens = _norm_topic_tokens(ch.title, ch.description, ch.primary_topic, ch.topic_search)
            seed_row_topics = _topics_from_row(ch)
            seed_union_tokens = seed_text_tokens | seed_row_topics
            seed_anchor_tokens = _norm_topic_tokens(ch.primary_topic, ch.topic_search)
            if not seed_topics:
                seed_topics = set(seed_row_topics)

            cat_rows = await self._channels.list_excluding_for_similarity(int(seed_channel_id), limit=400)
            added_catalog = 0
            for row in cat_rows:
                if row.id in cand_by_channel:
                    continue
                cand_tokens = _norm_topic_tokens(row.title, row.description, row.primary_topic, row.topic_search)
                cand_row_topics = _topics_from_row(row)
                union_c = cand_tokens | cand_row_topics
                text_sim = _jaccard(seed_union_tokens, union_c)
                topic_anchor_overlap = bool(seed_anchor_tokens & (cand_tokens | cand_row_topics))
                if seed_anchor_tokens and not topic_anchor_overlap and text_sim < 0.18:
                    continue
                if text_sim < 0.04 and not (seed_row_topics and cand_row_topics & seed_row_topics):
                    continue
                base = 0.18 + 0.62 * float(text_sim)
                merged_topics = set(cand_row_topics) | cand_tokens
                cand_by_channel[row.id] = {
                    "scores": [min(0.92, base)],
                    "topics": merged_topics,
                    "tones": set(),
                    "catalog_only": True,
                }
                added_catalog += 1
            if added_catalog:
                quality_notes.append(
                    f"Для {added_catalog} кандидатов использован запасной портрет по данным каталога "
                    "(без сводок постов в векторной базе)."
                )

            logger.info("similar.reranking seed_channel_id=%s candidates=%s", ch.id, len(cand_by_channel))
            seed_freq = float(ch.posts_per_week_estimate or 0.0)
            reranked: list[dict[str, Any]] = []
            filtered_out_by_topic = 0
            for cid, e in cand_by_channel.items():
                row = await self._channels.get_by_id(cid)
                if row is None:
                    continue
                cand_topic_set = set(e["topics"])
                row_catalog_tokens = _norm_topic_tokens(row.title, row.description, row.primary_topic, row.topic_search)
                topic_overlap = max(_jaccard(seed_topics, cand_topic_set), _jaccard(seed_row_topics, _topics_from_row(row)))
                anchor_overlap = _jaccard(seed_anchor_tokens, row_catalog_tokens) if seed_anchor_tokens else 0.0
                style_similarity = (
                    1.0
                    if seed_tones and set(e["tones"]) and (seed_tones & set(e["tones"]))
                    else (0.52 if e["catalog_only"] else 0.45)
                )
                frequency_similarity = _freq_sim(seed_freq, row.posts_per_week_estimate)
                base_similarity = max(e["scores"]) if e["scores"] else 0.0
                if seed_anchor_tokens and anchor_overlap < 0.01 and topic_overlap < 0.08 and base_similarity < 0.6:
                    filtered_out_by_topic += 1
                    continue
                score = (
                    0.58 * base_similarity
                    + 0.20 * topic_overlap
                    + 0.12 * style_similarity
                    + 0.10 * frequency_similarity
                )
                score_points = {
                    "sem": 58.0 * base_similarity,
                    "topic": 20.0 * topic_overlap,
                    "style": 12.0 * style_similarity,
                    "freq": 10.0 * frequency_similarity,
                }
                reasons: list[str] = []
                overlap_tokens = _top_overlap_tokens(seed_union_tokens, cand_topic_set | row_catalog_tokens)
                if overlap_tokens:
                    reasons.append(f"Общие темы: {', '.join(overlap_tokens)}.")
                if e.get("catalog_only"):
                    reasons.append("Канал подобран по карточке каталога: пока без сводок постов в Qdrant.")
                if style_similarity >= 0.8:
                    reasons.append("Похожий тон публикаций по сводкам.")
                if frequency_similarity >= 0.7:
                    reasons.append("Сопоставимая частота публикаций.")
                reasons.append(
                    "Оценка: "
                    f"{int(round(score * 100))}% = семантика {int(round(score_points['sem']))}п + "
                    f"темы {int(round(score_points['topic']))}п + стиль {int(round(score_points['style']))}п + "
                    f"частота {int(round(score_points['freq']))}п."
                )
                if not reasons:
                    reasons.append("Сходство по совокупности признаков.")
                missing_data: list[str] = []
                if e.get("catalog_only"):
                    missing_data.append("В Qdrant нет сводок постов по этому каналу — рекомендация опирается на каталог.")
                if not e["scores"] or (max(e["scores"]) < 0.25 and not e.get("catalog_only")):
                    missing_data.append("Низкая уверенность: мало пересечений в векторных сводках.")
                reranked.append(
                    {
                        "channel_id": cid,
                        "row": row,
                        "score": max(0.0, min(1.0, score)),
                        "catalog_only": bool(e.get("catalog_only")),
                        "signals": SimilarChannelSignals(
                            topic_overlap=round(float(topic_overlap), 4),
                            style_similarity=round(float(style_similarity), 4),
                            frequency_similarity=round(float(frequency_similarity), 4),
                        ),
                        "topics": list(sorted(set(e["topics"])))[:8],
                        "reasons": reasons,
                        "missing_data": missing_data,
                    }
                )
            if filtered_out_by_topic:
                quality_notes.append(
                    f"Отфильтровано {filtered_out_by_topic} кандидатов с тематикой, далёкой от исходного канала."
                )
            reranked.sort(key=lambda x: x["score"], reverse=True)

            logger.info("similar.diversification seed_channel_id=%s", ch.id)
            lam = 0.55
            selected: list[dict[str, Any]] = []
            remaining = reranked[: max(limit * 5, 20)]
            while remaining and len(selected) < limit:
                best_idx = 0
                best_val = float("-inf")
                for idx, cand in enumerate(remaining):
                    if not selected:
                        mmr_val = cand["score"]
                    else:
                        cand_topics = set(cand["topics"])
                        max_sim_to_selected = max(_jaccard(cand_topics, set(s["topics"])) for s in selected)
                        mmr_val = lam * cand["score"] - (1 - lam) * max_sim_to_selected
                    if mmr_val > best_val:
                        best_val = mmr_val
                        best_idx = idx
                selected.append(remaining.pop(best_idx))

            if not selected:
                return (
                    SimilarChannelsResponse(
                        needs_review=True,
                        reason="Не удалось подобрать похожие каналы по текущим данным каталога и векторной базы.",
                        mode=None,
                        source_channel=SimilarSourceChannel(channel_id=ch.id, channel_username=ch.username),
                        results=[],
                        quality_notes=quality_notes,
                    ),
                    None,
                )

            results = [
                SimilarChannelItem(
                    channel_id=int(x["channel_id"]),
                    channel_username=(x["row"].username if x["row"] else None),
                    title=(x["row"].title if x["row"] else None),
                    score=round(float(x["score"]), 4),
                    reasons=list(x["reasons"]),
                    supporting_topics=list(x["topics"]),
                    supporting_signals=x["signals"],
                    missing_data=list(x["missing_data"]),
                )
                for x in selected[:limit]
            ]
            logger.info("similar.response_building seed_channel_id=%s results=%s", ch.id, len(results))
            return (
                SimilarChannelsResponse(
                    needs_review=False,
                    reason=None,
                    mode="similar_channels",
                    source_channel=SimilarSourceChannel(
                        channel_id=ch.id,
                        channel_username=ch.username,
                    ),
                    results=results,
                    quality_notes=quality_notes,
                ),
                None,
            )
        finally:
            await qdrant.close()
