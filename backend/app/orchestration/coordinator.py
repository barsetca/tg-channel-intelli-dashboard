"""
Координатор фоновых пайплайнов (MVP: in-process asyncio; в проде — Celery/RQ/Arq).

================================================================================
EVENT FLOW (логическая шина)
================================================================================

1) **Discovery / ingestion (Telethon)**  
   Событие: ``CHANNEL_DISCOVERY_REQUESTED`` (payload: topic, filters).  
   Обработчик: Telethon-клиент ищет публичные сущности, нормализует в DTO каналов/постов.

2) **SQLite persistence**  
   Событие: ``CHANNEL_RECORD_UPSERTED`` / ``POST_BATCH_INSERTED``.  
   Обработчик: репозитории пишут ``Channel``, ``Post``, статусы синка.

3) **Metrics engine**  
   Событие: ``RAW_POSTS_AVAILABLE``.  
   Обработчик: пересчёт ``posts_per_week_estimate``, агрегаты подписчиков, last_post_at.

4) **AI pipeline**  
   Событие: ``METRICS_STABLE`` (или по расписанию).  
   Обработчик: ``ChannelAnalysisPipeline`` / сводки; результат в ``Analysis`` + текстовые артефакты.

5) **Vector search**  
   Событие: ``TEXT_CHUNKS_READY``.  
   Обработчик: chunking + embeddings → upsert в Qdrant (``VectorService``).

Зависимости между этапами: (1)→(2)→(3) часто линейны; (4) и (5) могут идти параллельно
после (3), если нет жёсткой связи «анализ ждёт метрик».

================================================================================
BACKGROUND JOBS
================================================================================

* **telegram_channel_discovery** — очередь на поиск новых каналов в Telegram и запись в каталог.  
* **channel_resync** (зарезервировано) — догрузка постов для существующего канала.  
* **metrics_rebuild** (зарезервировано) — пакетный пересчёт метрик.  
* **vector_reindex** (зарезервировано) — переиндексация чанков.

В этом MVP воркер только симулирует стадии (лог + ``asyncio.sleep``), чтобы зафиксировать
контракт ``job_id`` / ``status`` для API и дальнейшей замены на реальные воркеры.

================================================================================
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
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Короткие id для API + подписи для логов/UI
_STAGE_LABELS: dict[str, str] = {
    "telethon_ingest": "Telethon: поиск каналов в Telegram",
    "sqlite_persist": "SQLite: запись в каталог",
    "metrics": "Метрики (посты/неделя, агрегаты)",
    "ai_pipeline": "AI-пайплайн",
    "vector_index": "Векторный индекс (эмбеддинги / Qdrant)",
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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


StageHandler = Callable[[OrchestrationJob], Awaitable[None]]


class OrchestrationCoordinator:
    """
    Точка входа для постановки фоновых заданий и последовательной обработки очереди.

    Не держит ``AsyncSession``: персистентность делегируется воркерам с собственными
    сессиями (избегаем утечки транзакций HTTP-запроса в фон).
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[OrchestrationJob] | None = None
        self._jobs: dict[str, OrchestrationJob] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._stage_handlers: dict[OrchestrationJobKind, list[tuple[str, StageHandler]]] = {
            OrchestrationJobKind.TELEGRAM_CHANNEL_DISCOVERY: [
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

    async def schedule_telegram_channel_discovery(self, *, payload: dict[str, Any]) -> str:
        """
        Ставит в очередь поиск каналов в Telegram по критериям ``payload``
        (topic, count, язык, регион и т.д., сериализованные из ``SearchChannelsRequest``).
        """
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
            except Exception as exc:  # noqa: BLE001 — воркер не падает
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
        job.detail = "Пайплайн завершён (MVP: стадии-заглушки; см. логи orchestration.stage_*)."
        job.updated_at = datetime.now(timezone.utc)
        logger.info("orchestration.job_completed job_id=%s", job.id)

    async def _stage_telethon_ingest(self, job: OrchestrationJob) -> None:
        """Стадия 1: Telethon discovery (заглушка — здесь вызывается реальный Telethon-клиент)."""
        await asyncio.sleep(0.05)
        logger.info(
            "orchestration.stage telethon_ingest job_id=%s topic=%r keys=%s",
            job.id,
            job.payload.get("topic"),
            sorted(job.payload.keys()),
        )

    async def _stage_sqlite_persist(self, job: OrchestrationJob) -> None:
        """Стадия 2: запись в SQLite через репозитории (заглушка)."""
        await asyncio.sleep(0.03)
        logger.info("orchestration.stage sqlite_persist job_id=%s", job.id)

    async def _stage_metrics(self, job: OrchestrationJob) -> None:
        """Стадия 3: metrics engine (частота постов, агрегаты)."""
        await asyncio.sleep(0.02)
        logger.info("orchestration.stage metrics job_id=%s", job.id)

    async def _stage_ai_pipeline(self, job: OrchestrationJob) -> None:
        """Стадия 4: LLM / анализ (заглушка — не блокируем HTTP)."""
        await asyncio.sleep(0.02)
        logger.info("orchestration.stage ai_pipeline job_id=%s", job.id)

    async def _stage_vector_index(self, job: OrchestrationJob) -> None:
        """Стадия 5: embeddings + vector upsert (заглушка)."""
        await asyncio.sleep(0.02)
        logger.info("orchestration.stage vector_index job_id=%s", job.id)
