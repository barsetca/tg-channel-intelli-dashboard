"""
Сценарий 1 — фоновый пайплайн telegram_live: Planner → Telethon → SQLite + audit → метрики → AI → vector.

Без циклического импорта ``coordinator``: job — объект с полями ``id``, ``payload``, ``planner_output``, ``transient``.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import PayloadSchemaType
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas.search_planner import SearchPlannerOutput
from app.core.config import Settings
from app.core.database import AsyncSessionLocal
from app.integrations.openai_client import OpenAIClient
from app.integrations.qdrant_client import QdrantStore
from app.integrations.telethon import TelethonUserSessionService
from app.integrations.telethon.dto import TelegramSearchHit
from app.models.audit_run import AuditRun
from app.models.audit_run_item import AuditRunItem
from app.repositories.channel_repository import ChannelRepository
from app.services.channel_search_planner import merge_planner_with_user_request, plan_channel_search

PROFILE_COLLECTION = "telegram_channel_profiles"

logger = logging.getLogger(__name__)

# Лимиты защиты от бесконечных циклов и слишком тяжёлых burst-запросов к Telegram.
_MAX_SEARCH_LIMIT = 100
_MAX_UNIQUE_CANDIDATES = 450
_MAX_QUERY_VARIANTS = 14
_MAX_QUERY_VARIANTS_STRICT = 28
_ENRICH_CONCURRENCY = 6
_ENRICH_BATCH = 18


def _subscriber_filters_active(merged: dict[str, Any] | None) -> bool:
    if not merged:
        return False
    ms, xs = merged.get("min_subscribers"), merged.get("max_subscribers")
    return isinstance(ms, int) or isinstance(xs, int)


def _unique_hit_collection_cap(target: int, merged: dict[str, Any]) -> int:
    """
    Сколько уникальных chat_id собрать из contacts.Search до остановки.
    При узком диапазоне подписчиков выдача Telegram редко попадает в бэнды — нужно больше сырых кандидатов.
    """
    # В Telegram live фильтр по подписчикам отключён: contacts.Search не умеет этот фильтр нативно.
    min_sub = None
    max_sub = None
    base = max(80, target * 25)
    if not _subscriber_filters_active(merged):
        return min(_MAX_UNIQUE_CANDIDATES, base)
    if isinstance(min_sub, int) and isinstance(max_sub, int):
        band = max(1, int(max_sub) - int(min_sub))
        boost = min(10, max(2, 80_000 // band))
        scaled = base * boost
    else:
        scaled = max(base, target * 50, 400)
    return min(_MAX_UNIQUE_CANDIDATES, scaled)


def _search_query_variants(
    planner_topic: str,
    user_topic: str,
    merged: dict[str, Any] | None = None,
) -> list[str]:
    """
    Несколько формулировок глобального поиска: Telegram не пагинирует contacts.Search.

    При фильтре min/max подписчиков добавляем варианты: API не фильтрует по числу подписчиков
    (в отличие от каталогов вроде TGStat), без расширения запросов почти все кандидаты
    отсекаются уже на нашей стороне после get_channel_info.
    """
    strict = _subscriber_filters_active(merged)
    cap = _MAX_QUERY_VARIANTS_STRICT if strict else _MAX_QUERY_VARIANTS
    seen: set[str] = set()
    out: list[str] = []

    def add(q: str) -> None:
        q = (q or "").strip()
        if len(q) < 2:
            return
        key = q.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(q)

    add(planner_topic)
    add(user_topic)
    base = planner_topic.strip()
    if base:
        add(f"{base} канал")
        add(f"{base} channel")
        add(f"{base} news")
        add(f"{base} telegram")
    for sep in (" & ", " and ", " / ", " | ", ",", " и "):
        if sep in planner_topic:
            for part in planner_topic.split(sep):
                add(part.strip())
        if sep in user_topic:
            for part in user_topic.split(sep):
                add(part.strip())

    if strict:
        for raw in (planner_topic.strip(), user_topic.strip()):
            if len(raw) < 2:
                continue
            add(f"канал {raw}")
            add(f"каналы {raw}")
            add(f"про {raw}")
            add(f"{raw} телеграм")
            add(f"{raw} telegram")
            add(f"{raw} ии")
            add(f"{raw} ai")
            add(f"топ {raw}")
            add(f"{raw} новости")
            add(f"{raw} гайд")
    return out[:cap]


async def run_planner_stage(settings: Settings, job: Any) -> None:
    out = await plan_channel_search(settings, dict(job.payload))
    job.planner_output = out.model_dump()
    logger.info("discovery.planner job_id=%s search_topic=%r count=%s", job.id, out.search_topic, out.count)


async def run_telethon_stage(
    settings: Settings,
    telegram: TelethonUserSessionService | None,
    job: Any,
) -> None:
    _ = settings
    if telegram is None:
        raise RuntimeError("Telegram сервис недоступен — live discovery невозможен.")

    planner = SearchPlannerOutput.model_validate(job.planner_output or {})
    merged = merge_planner_with_user_request(dict(job.payload), planner)
    job.transient["merged_params"] = merged

    query = str(merged.get("search_topic") or "").strip()
    if not query:
        raise RuntimeError("Пустой search_topic после планировщика.")

    target = max(1, min(15, int(merged.get("count") or 15)))
    user_topic = str(job.payload.get("topic") or "").strip()
    username_query = str(job.payload.get("username_query") or "").strip()
    live_mode = str(job.payload.get("live_channel_mode") or "new").strip().lower()
    selected_channel_ids = [int(x) for x in (job.payload.get("selected_channel_ids") or []) if int(x) > 0]
    variants = _search_query_variants(query, user_topic, merged)
    hit_cap = _unique_hit_collection_cap(target, merged)
    per_query_limit = min(_MAX_SEARCH_LIMIT, max(40, target * 8))
    if _subscriber_filters_active(merged):
        per_query_limit = _MAX_SEARCH_LIMIT

    diagnostics: dict[str, Any] = {
        "primary_query": query,
        "user_topic": user_topic,
        "target_count": target,
        "per_query_limit": per_query_limit,
        "unique_hit_cap": hit_cap,
        "subscriber_filters_active": _subscriber_filters_active(merged),
        "queries_tried": [],
        "unique_candidates": 0,
        "raw_hits": 0,
        "enriched_hits": 0,
        "skipped": {
            "private_or_left": 0,
            "new_only_existing": 0,
            "min_subscribers": 0,
            "max_subscribers": 0,
            "other": 0,
        },
        "sample_errors": [],
    }

    min_sub = merged.get("min_subscribers")
    max_sub = merged.get("max_subscribers")
    new_only = merged.get("channel_type") == "new_only"
    if username_query or live_mode == "saved":
        # Для точечного username-поиска и актуализации выбранных сохранённых каналов
        # не отбрасываем уже существующие каналы: требуется update-or-insert.
        new_only = False

    seen_hit_ids: set[int] = set()
    ordered_hits: list[TelegramSearchHit] = []
    if username_query:
        ident = username_query.lstrip("@")
        info = await telegram.get_channel_info(ident)
        ordered_hits.append(
            TelegramSearchHit(
                telegram_channel_id=int(info.telegram_channel_id),
                username=info.username,
                title=info.title,
                is_broadcast=True,
            )
        )
        diagnostics["queries_tried"].append({"q": f"@{ident}", "hits": 1, "mode": "username"})
    elif live_mode == "saved" and selected_channel_ids:
        async with AsyncSessionLocal() as session:
            repo = ChannelRepository(session)
            rows = await repo.list_by_ids_ordered(selected_channel_ids)
        for row in rows:
            ordered_hits.append(
                TelegramSearchHit(
                    telegram_channel_id=int(row.telegram_id),
                    username=row.username,
                    title=row.title,
                    is_broadcast=True,
                )
            )
        target = min(20, max(1, len(ordered_hits)))
        diagnostics["queries_tried"].append({"q": "selected_saved_channels", "hits": len(ordered_hits), "mode": "saved"})
    else:
        for qv in variants:
            if len(ordered_hits) >= _MAX_UNIQUE_CANDIDATES:
                break
            hits = await telegram.search_public_channels(qv, limit=per_query_limit, broadcast_only=True)
            diagnostics["queries_tried"].append({"q": qv, "hits": len(hits)})
            diagnostics["raw_hits"] += len(hits)
            for h in hits:
                tid = int(h.telegram_channel_id)
                if tid in seen_hit_ids:
                    continue
                seen_hit_ids.add(tid)
                ordered_hits.append(h)
            if len(ordered_hits) >= hit_cap:
                break

    diagnostics["unique_candidates"] = len(ordered_hits)
    logger.info(
        "discovery.telethon job_id=%s target=%s unique_candidates=%d variants=%d",
        job.id,
        target,
        len(ordered_hits),
        len(diagnostics["queries_tried"]),
    )

    existing_in_db: set[int] = set()
    if new_only and ordered_hits:
        all_ids = [int(h.telegram_channel_id) for h in ordered_hits]
        async with AsyncSessionLocal() as session:
            repo = ChannelRepository(session)
            for i in range(0, len(all_ids), 400):
                chunk = all_ids[i : i + 400]
                existing_in_db |= await repo.existing_telegram_ids_among(chunk)

    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def enrich(hit: TelegramSearchHit) -> dict[str, Any] | None:
        async with sem:
            ident: str | int = hit.username if hit.username else hit.telegram_channel_id
            try:
                info = await telegram.get_channel_info(ident)
            except Exception as exc:  # noqa: BLE001
                logger.warning("discovery.telethon get_channel_info skip id=%s: %s", ident, exc)
                err = str(exc).lower()
                if "left/private" in err or "private" in err or "недоступен" in err:
                    diagnostics["skipped"]["private_or_left"] += 1
                else:
                    diagnostics["skipped"]["other"] += 1
                if len(diagnostics["sample_errors"]) < 5:
                    diagnostics["sample_errors"].append(f"{ident}: {exc}")
                return None
            tid = int(info.telegram_channel_id)
            if new_only and tid in existing_in_db:
                diagnostics["skipped"]["new_only_existing"] += 1
                return None
            subs = info.participants_count
            if isinstance(min_sub, int) and subs is not None and subs < min_sub:
                diagnostics["skipped"]["min_subscribers"] += 1
                return None
            if isinstance(max_sub, int) and subs is not None and subs > max_sub:
                diagnostics["skipped"]["max_subscribers"] += 1
                return None
            slug = f"@{info.username}" if info.username else None
            return {
                "telegram_id": tid,
                "username": info.username,
                "title": info.title,
                "description": info.about,
                "subscriber_count": subs,
                "invite_slug": slug,
                "primary_topic": str(merged.get("search_topic") or "")[:512] or None,
                "topic_search": str(job.payload.get("topic") or "")[:512] or None,
                "language_hint": merged.get("language"),
                "region_country": merged.get("region_country"),
            }

    normalized: list[dict[str, Any]] = []
    for i in range(0, len(ordered_hits), _ENRICH_BATCH):
        if len(normalized) >= target:
            break
        batch = ordered_hits[i : i + _ENRICH_BATCH]
        rows = await asyncio.gather(*[enrich(h) for h in batch])
        for row in rows:
            if row is None:
                continue
            normalized.append(row)
            if len(normalized) >= target:
                break

    normalized = normalized[:target]
    job.transient["normalized_channels"] = normalized
    diagnostics["enriched_hits"] = len(normalized)
    diagnostics["underfilled"] = len(normalized) < target
    skip_total = sum(int(v) for v in diagnostics["skipped"].values())
    diagnostics["skipped_total"] = skip_total
    if skip_total > 0:
        top = Counter({k: int(v) for k, v in diagnostics["skipped"].items() if int(v) > 0}).most_common(3)
        diagnostics["top_skip_reasons"] = [f"{k}={v}" for k, v in top]
    job.transient["discovery_diagnostics"] = diagnostics
    logger.info("discovery.telethon job_id=%s enriched=%d target=%s", job.id, len(normalized), target)


async def run_sqlite_persist_stage(session: AsyncSession, job: Any) -> None:
    rows: list[dict[str, Any]] = job.transient.get("normalized_channels") or []
    repo = ChannelRepository(session)
    started_at = datetime.now(timezone.utc)
    input_payload = dict(job.payload)

    audit = AuditRun(
        audit_kind="channel_discovery",
        action="telegram_live_discovery",
        status="running",
        raw_user_input_json=input_payload,
        input_json=input_payload,
        planner_output_json=dict(job.planner_output) if job.planner_output else None,
    )
    session.add(audit)
    await session.flush()

    channel_ids_ordered: list[int] = []
    for order, row in enumerate(rows):
        ch = await repo.upsert_discovery_channel(
            telegram_id=int(row["telegram_id"]),
            username=row.get("username"),
            title=row.get("title"),
            description=row.get("description"),
            subscriber_count=row.get("subscriber_count"),
            invite_slug=row.get("invite_slug"),
            primary_topic=row.get("primary_topic"),
            topic_search=row.get("topic_search"),
            language_hint=row.get("language_hint"),
            region_country=row.get("region_country"),
        )
        channel_ids_ordered.append(ch.id)
        snap = {
            "telegram_id": ch.telegram_id,
            "username": ch.username,
            "title": ch.title,
            "description": ch.description,
            "subscriber_count": ch.subscriber_count,
            "invite_slug": ch.invite_slug,
            "primary_topic": ch.primary_topic,
            "topic_search": ch.topic_search,
            "language_hint": ch.language_hint,
            "region_country": ch.region_country,
        }
        session.add(
            AuditRunItem(
                audit_run_id=int(audit.id),
                entity_kind="channel_candidate",
                channel_id=ch.id,
                display_order=order,
                relevance_score=Decimal("0"),
                snapshot_json=snap,
                telegram_username_fallback=ch.username,
            )
        )

    summary = {
        "channels_saved": len(rows),
        "orchestration_job_id": job.id,
        "audit_run_id": audit.id,
        "discovery_diagnostics": job.transient.get("discovery_diagnostics"),
    }
    audit.status = "completed"
    audit.result_summary_json = summary
    audit.output_json = summary
    audit.duration_ms = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000))
    await session.commit()
    job.transient["persisted_channel_ids"] = channel_ids_ordered
    job.transient["audit_run_id"] = int(audit.id)
    logger.info("discovery.sqlite job_id=%s saved=%d audit_run_id=%s", job.id, len(rows), audit.id)


async def run_metrics_stage(
    settings: Settings,
    telegram: TelethonUserSessionService | None,
    job: Any,
) -> None:
    _ = settings
    if telegram is None:
        return
    ids: list[int] = job.transient.get("persisted_channel_ids") or []
    if not ids:
        return

    async with AsyncSessionLocal() as session:
        repo = ChannelRepository(session)
        for cid in ids[:20]:
            ch = await repo.get_by_id(cid)
            if ch is None:
                continue
            ident: str | int = ch.username if ch.username else ch.telegram_id
            try:
                posts = await telegram.fetch_recent_posts(ident, limit=15)
            except Exception as exc:  # noqa: BLE001
                logger.warning("discovery.metrics posts job_id=%s ch=%s: %s", job.id, cid, exc)
                continue
            if not posts:
                continue
            last_dt = max(p.date_utc for p in posts if p.date_utc)
            first_dt = min(p.date_utc for p in posts if p.date_utc)
            ch.last_post_at = last_dt
            span_days = max((last_dt - first_dt).total_seconds() / 86400.0, 0.25)
            weeks = max(span_days / 7.0, 0.05)
            ch.posts_per_week_estimate = round(len(posts) / weeks, 3)
            await session.flush()
        await session.commit()
    logger.info("discovery.metrics job_id=%s updated_channels=%d", job.id, min(len(ids), 20))


async def run_ai_stage(settings: Settings, job: Any) -> None:
    """Лёгкая нормализация primary_topic через LLM при наличии ключа; иначе пропуск."""
    if not settings.openai_api_key:
        return
    ids: list[int] = job.transient.get("persisted_channel_ids") or []
    if not ids:
        return
    try:
        from openai.types.chat import ChatCompletionDeveloperMessageParam, ChatCompletionUserMessageParam

        from app.ai.clients.openai_chat import OpenAIStageClient
        from app.ai.orchestration.errors import PipelineOpenAIError

        client = OpenAIStageClient(settings)
    except Exception as exc:  # noqa: BLE001
        logger.info("discovery.ai skipped job_id=%s: %s", job.id, exc)
        return

    async with AsyncSessionLocal() as session:
        repo = ChannelRepository(session)
        topic_hint = str((job.transient.get("merged_params") or {}).get("search_topic") or "")[:200]
        for cid in ids[:25]:
            ch = await repo.get_by_id(cid)
            if ch is None or (ch.title or "") == "":
                continue
            blob = f"title={ch.title!r}\ndescription={(ch.description or '')[:800]}"
            messages = [
                ChatCompletionDeveloperMessageParam(
                    role="developer",
                    content="Верни одну короткую строку (2–5 слов) — тематику канала на русском или английском.",
                ),
                ChatCompletionUserMessageParam(
                    role="user",
                    content=f"Контекст ниши пользователя: {topic_hint}\n\n{blob}",
                ),
            ]
            try:
                label = (await client.complete_text(messages=messages)).strip()[:512]
            except PipelineOpenAIError as exc:
                logger.warning("discovery.ai label ch=%s: %s", cid, exc)
                continue
            if label:
                ch.primary_topic = label
                await session.flush()
        await session.commit()
    logger.info("discovery.ai job_id=%s finished", job.id)


async def run_vector_stage(settings: Settings, job: Any) -> None:
    """
    Индексация «лёгкого» профиля канала в Qdrant для сценария 6 (похожие каналы).

    Берутся title/description/primary_topic/topic_search из SQLite сразу после discovery,
    без обязательного сценария 3 — сводки постов по-прежнему улучшают точность, но не обязательны.
    """
    if not settings.openai_api_key or not settings.qdrant_url:
        logger.info("discovery.vector skipped (no OpenAI/Qdrant config)")
        return
    ids: list[int] = job.transient.get("persisted_channel_ids") or []
    if not ids:
        return

    openai = OpenAIClient()
    qdr = QdrantStore(settings)
    try:
        texts: list[str] = []
        metas: list[Any] = []
        async with AsyncSessionLocal() as session:
            repo = ChannelRepository(session)
            for cid in ids:
                ch = await repo.get_by_id(cid)
                if ch is None:
                    continue
                blob = "\n".join(
                    str(x).strip()
                    for x in (ch.title, ch.description, ch.primary_topic, ch.topic_search)
                    if x and str(x).strip()
                )
                if len(blob) < 8:
                    continue
                texts.append(blob[: settings.embedding_max_chunk_chars])
                metas.append(ch)
        if not texts:
            logger.info("discovery.vector job_id=%s no profile text to embed", job.id)
            return

        vectors = await openai.embed_texts(texts)
        dim = len(vectors[0])
        await qdr.ensure_collection_named(PROFILE_COLLECTION, dim)
        for field_name, field_type in (
            ("channel_id", PayloadSchemaType.INTEGER),
            ("entity_type", PayloadSchemaType.KEYWORD),
            ("channel_username", PayloadSchemaType.KEYWORD),
        ):
            try:
                await qdr.ensure_payload_index(
                    collection_name=PROFILE_COLLECTION,
                    field_name=field_name,
                    field_type=field_type,
                )
            except Exception:  # noqa: BLE001
                pass

        point_ids: list[str] = []
        out_vectors: list[list[float]] = []
        payloads: list[dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for ch, vec in zip(metas, vectors, strict=True):
            pid = str(uuid5(NAMESPACE_URL, f"{PROFILE_COLLECTION}/v1|channel_id={ch.id}"))
            point_ids.append(pid)
            out_vectors.append(vec)
            payloads.append(
                {
                    "entity_type": "channel_profile",
                    "channel_id": int(ch.id),
                    "channel_username": (ch.username or "").lstrip("@") or None,
                    "language": ch.language_hint,
                    "generated_at": now_iso,
                    "profile_version": 1,
                    "source": "discovery_pipeline",
                }
            )
        await qdr.upsert_vectors_to(
            collection_name=PROFILE_COLLECTION,
            ids=point_ids,
            vectors=out_vectors,
            payloads=payloads,
        )
        logger.info(
            "discovery.vector job_id=%s indexed_profiles=%s collection=%s",
            job.id,
            len(point_ids),
            PROFILE_COLLECTION,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery.vector job_id=%s failed: %s", job.id, exc)
    finally:
        await qdr.close()
