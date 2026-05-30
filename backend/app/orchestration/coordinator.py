"""
Координатор фоновых пайплайнов (in-process asyncio).

Сценарий 1 (telegram_live): Planner → Telethon → SQLite + audit_runs → метрики → AI → vector (заглушка vector).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.core.config import Settings, get_settings
from app.orchestration import discovery_pipeline

if TYPE_CHECKING:
    from app.integrations.telethon import TelethonUserSessionService

logger = logging.getLogger(__name__)

_STAGE_LABELS: dict[str, str] = {
    "planner": "AI Planner: структурирование запроса",
    "telethon_ingest": "Telethon: поиск каналов в Telegram",
    "sqlite_persist": "SQLite: запись в каталог и audit_runs",
    "metrics": "Метрики (посты/неделя, last_post_at)",
    "ai_pipeline": "AI: уточнение тематики каналов",
    "vector_index": "Векторный индекс (при необходимости)",
}


class OrchestrationJobKind(str, Enum):
    TELEGRAM_CHANNEL_DISCOVERY = "telegram_channel_discovery"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OrchestrationJob:
    id: str
    kind: OrchestrationJobKind
    payload: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    detail: str = ""
    stage: str | None = None
    stage_label: str | None = None
    planner_output: dict[str, Any] | None = None
    transient: dict[str, Any] = field(default_factory=dict, repr=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


StageHandler = Callable[[OrchestrationJob], Awaitable[None]]


class OrchestrationCoordinator:
    """
    Очередь заданий и воркер. Сессии БД открываются внутри стадий (не в HTTP-транзакции).
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        get_telegram: Callable[[], "TelethonUserSessionService | None"] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._get_telegram: Callable[[], Any] = get_telegram or (lambda: None)
        self._queue: asyncio.Queue[OrchestrationJob] | None = None
        self._jobs: dict[str, OrchestrationJob] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._stage_handlers: dict[OrchestrationJobKind, list[tuple[str, StageHandler]]] = {
            OrchestrationJobKind.TELEGRAM_CHANNEL_DISCOVERY: [
                ("planner", self._stage_planner),
                ("telethon_ingest", self._stage_telethon_ingest),
                ("sqlite_persist", self._stage_sqlite_persist),
                ("metrics", self._stage_metrics),
                ("ai_pipeline", self._stage_ai_pipeline),
                ("vector_index", self._stage_vector_index),
            ],
        }

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._queue = asyncio.Queue()
        self._stopped.clear()
        self._worker_task = asyncio.create_task(self._worker_loop(), name="orchestration-worker")

    async def stop(self) -> None:
        self._stopped.set()
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        self._queue = None

    def get_job(self, job_id: str) -> OrchestrationJob | None:
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> OrchestrationJob | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            return job
        job.transient["cancel_requested"] = True
        job.detail = "Отмена запрошена пользователем. Ожидаем остановку задания."
        job.updated_at = datetime.now(timezone.utc)
        logger.info("orchestration.job_cancel_requested job_id=%s status=%s", job.id, job.status.value)
        return job

    async def schedule_telegram_channel_discovery(self, *, payload: dict[str, Any]) -> str:
        if self._queue is None:
            raise RuntimeError("OrchestrationCoordinator.start() must run before scheduling jobs")
        job_id = str(uuid.uuid4())
        job = OrchestrationJob(
            id=job_id,
            kind=OrchestrationJobKind.TELEGRAM_CHANNEL_DISCOVERY,
            payload=payload,
            detail="В очереди воркера оркестратора (ещё не взято в работу).",
        )
        self._jobs[job_id] = job
        await self._queue.put(job)
        logger.info("orchestration.job_enqueued job_id=%s kind=%s topic=%r", job_id, job.kind, payload.get("topic"))
        return job_id

    async def _worker_loop(self) -> None:
        queue = self._queue
        assert queue is not None
        while not self._stopped.is_set():
            try:
                job = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            logger.info("orchestration.job_dequeued job_id=%s kind=%s", job.id, job.kind)
            try:
                await self._run_job(job)
            except Exception as exc:  # noqa: BLE001
                job.status = JobStatus.FAILED
                job.detail = str(exc)
                job.stage = None
                job.stage_label = None
                job.updated_at = datetime.now(timezone.utc)
                logger.exception("orchestration.job_failed job_id=%s", job.id)

    async def _run_job(self, job: OrchestrationJob) -> None:
        job.status = JobStatus.RUNNING
        job.detail = "Воркер запустил пайплайн."
        job.stage = None
        job.stage_label = None
        job.updated_at = datetime.now(timezone.utc)
        stages = self._stage_handlers.get(job.kind, [])
        logger.info("orchestration.job_started job_id=%s stages=%d", job.id, len(stages))
        for stage_id, handler in stages:
            if job.transient.get("cancel_requested"):
                raise RuntimeError("Задание отменено пользователем.")
            label = _STAGE_LABELS.get(stage_id, stage_id)
            job.stage = stage_id
            job.stage_label = label
            job.detail = f"Выполняется: {label}"
            job.updated_at = datetime.now(timezone.utc)
            logger.info("orchestration.stage_begin job_id=%s stage=%s", job.id, stage_id)
            await handler(job)
            logger.info("orchestration.stage_end job_id=%s stage=%s", job.id, stage_id)
        job.status = JobStatus.COMPLETED
        job.stage = None
        job.stage_label = None
        saved = len(job.transient.get("normalized_channels", []))
        audit_id = job.transient.get("audit_run_id")
        diagnostics = job.transient.get("discovery_diagnostics") or {}
        raw_hits = diagnostics.get("raw_hits")
        unique_candidates = diagnostics.get("unique_candidates")
        skipped_total = diagnostics.get("skipped_total")
        top_reasons = diagnostics.get("top_skip_reasons") or []
        wanted = int((job.transient.get("merged_params") or {}).get("count") or saved)
        underfilled = bool(diagnostics.get("underfilled")) and saved < wanted
        if saved == 0:
            reason_text = ", ".join(str(x) for x in top_reasons) if top_reasons else "нет проходящих кандидатов после фильтров"
            job.detail = (
                f"Поиск в Telegram завершён без сохранённых каналов: hits_всего={raw_hits}, уникальных_кандидатов={unique_candidates}, "
                f"skipped={skipped_total}. Основные причины: {reason_text}. "
                "Рекомендации: ослабьте фильтры (язык/подписчики), поменяйте тему и проверьте, что сессия имеет доступ к публичным каналам."
            )
        elif underfilled:
            reason_text = ", ".join(str(x) for x in top_reasons) if top_reasons else "мало подходящих кандидатов"
            subs_hint = ""
            if top_reasons and any("subscribers" in str(x) for x in top_reasons):
                subs_hint = (
                    " contacts.Search не сужает по подписчикам и не индексирует описание как TGStat;"
                    " при узком диапазоне большинство кандидатов отсекается после get_channel_info."
                )
            new_only_hint = ""
            if top_reasons and any("new_only_existing" in str(x) for x in top_reasons):
                new_only_hint = (
                    " В режиме «Новые» каналы из каталога пропускаются;"
                    " если результатов меньше запрошенного — уточните тему или сузьте нишу."
                )
            job.detail = (
                f"Поиск в Telegram завершён: сохранено {saved} из запрошенных до {wanted}. "
                f"Уникальных кандидатов из поиска: {unique_candidates}, отсеяно: {skipped_total}. "
                f"Топ причин: {reason_text}. Попробуйте ослабить фильтры или расширить формулировку темы."
                f"{subs_hint}{new_only_hint}"
            )
        else:
            job.detail = (
                f"Поиск в Telegram завершён: обогащённых каналов {saved}, записано в SQLite и audit_runs "
                f"(audit_run_id={audit_id}). Дальше — просмотр в режиме «Saved catalog»."
            )
        job.updated_at = datetime.now(timezone.utc)
        logger.info("orchestration.job_completed job_id=%s saved=%s", job.id, saved)
        logger.info("orchestration.job_detail job_id=%s detail=%s", job.id, job.detail)
        logger.info("Идентификатор задания оркестратора: job_id=%s", job.id)

    async def _stage_planner(self, job: OrchestrationJob) -> None:
        await discovery_pipeline.run_planner_stage(self._settings, job)

    async def _stage_telethon_ingest(self, job: OrchestrationJob) -> None:
        await discovery_pipeline.run_telethon_stage(self._settings, self._get_telegram(), job)

    async def _stage_sqlite_persist(self, job: OrchestrationJob) -> None:
        from pathlib import Path

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.database import AsyncSessionLocal, settings as db_settings

        if self._settings.database_url == db_settings.database_url:
            async with AsyncSessionLocal() as session:
                await discovery_pipeline.run_sqlite_persist_stage(session, job)
            return

        # Для изолированных тестов/инстансов: используем БД из settings координатора, а не глобальный engine.
        if self._settings.database_url.startswith("sqlite+aiosqlite:///"):
            db_path = Path(self._settings.database_url.removeprefix("sqlite+aiosqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(self._settings.database_url, echo=False)
        session_local = async_sessionmaker(engine, expire_on_commit=False, autoflush=False, autocommit=False)
        try:
            async with session_local() as session:
                await discovery_pipeline.run_sqlite_persist_stage(session, job)
        finally:
            await engine.dispose()

    async def _stage_metrics(self, job: OrchestrationJob) -> None:
        await discovery_pipeline.run_metrics_stage(self._settings, self._get_telegram(), job)

    async def _stage_ai_pipeline(self, job: OrchestrationJob) -> None:
        await discovery_pipeline.run_ai_stage(self._settings, job)

    async def _stage_vector_index(self, job: OrchestrationJob) -> None:
        await discovery_pipeline.run_vector_stage(self._settings, job)
