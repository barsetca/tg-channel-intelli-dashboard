import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_run import AuditRun
from app.models.channel import Channel
from app.orchestration.coordinator import OrchestrationCoordinator
from app.repositories.channel_repository import ChannelRepository
from app.schemas.intelligence import SearchChannelsRequest
from app.schemas.channel import (
    ChannelCollectRequest,
    ChannelCollectResponse,
    ChannelCreate,
    ChannelCreateResult,
    ChannelListResponse,
    ChannelRead,
)

if TYPE_CHECKING:
    from app.services.intelligence_service import IntelligenceService

logger = logging.getLogger(__name__)


class ChannelService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        intelligence: "IntelligenceService | None" = None,
        coordinator: OrchestrationCoordinator | None = None,
    ) -> None:
        self._session = session
        self._channels = ChannelRepository(session)
        self._intelligence = intelligence
        self._coordinator = coordinator

    @staticmethod
    def _normalize_channel_ref(raw: str) -> str:
        v = (raw or "").strip()
        if v.startswith("https://t.me/"):
            v = v.replace("https://t.me/", "").split("/")[0]
        elif v.startswith("http://t.me/"):
            v = v.replace("http://t.me/", "").split("/")[0]
        elif v.startswith("t.me/"):
            v = v.replace("t.me/", "").split("/")[0]
        v = v.strip().lstrip("@")
        return v

    @staticmethod
    def _synthetic_telegram_id(ref: str) -> int:
        digest = hashlib.sha1(ref.encode("utf-8")).hexdigest()[:12]
        return int(digest, 16)

    async def _record_collect_error_audit(
        self,
        *,
        channel_id: int,
        row: Channel | None,
        body: ChannelCollectRequest,
        status: str,
        error_text: str,
        http_code: int,
    ) -> None:
        started_at = datetime.now(timezone.utc)
        payload = body.model_dump(mode="json")
        payload["channel_id"] = channel_id
        payload["username"] = row.username if row is not None else None
        audit = AuditRun(
            audit_kind="channel_discovery",
            action="dataset_collect_error",
            status=status,
            raw_user_input_json=payload,
            input_json=payload,
            output_json={"http_status": http_code, "error": error_text},
            result_summary_json={"source": "datasets_collect", "http_status": http_code},
            error=error_text,
            error_text=error_text,
            duration_ms=max(0, int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)),
        )
        self._session.add(audit)
        await self._session.commit()

    async def create_or_get(self, data: ChannelCreate) -> ChannelCreateResult:
        if data.telegram_id is not None:
            existing = await self._channels.get_by_telegram_id(int(data.telegram_id))
            if existing:
                return ChannelCreateResult(
                    id=int(existing.id),
                    username=existing.username,
                    sync_status=existing.sync_status,
                    already_exists=True,
                    message="Канал уже есть в базе данных. Новая запись не создавалась.",
                )
        ref = self._normalize_channel_ref(data.channel_ref or data.username or "")
        if ref:
            by_uname = await self._channels.get_by_username(ref)
            if by_uname:
                return ChannelCreateResult(
                    id=int(by_uname.id),
                    username=by_uname.username,
                    sync_status=by_uname.sync_status,
                    already_exists=True,
                    message="Канал уже есть в базе данных. Новая запись не создавалась.",
                )

        telegram_id = int(data.telegram_id) if data.telegram_id is not None else self._synthetic_telegram_id(ref or "draft")
        username = ref or data.username
        extras = {"dataset_extra_query": (data.extra_conditions or "").strip() or None}
        channel = Channel(
            telegram_id=telegram_id,
            username=username,
            title=data.title or (f"@{username}" if username else "Новый канал"),
            description=data.description,
            topic_search=(data.topic_search or "").strip() or None,
            sync_status="draft",
            extras_json=extras,
        )
        await self._channels.add(channel)
        await self._session.commit()
        return ChannelCreateResult(
            id=int(channel.id),
            username=channel.username,
            sync_status=channel.sync_status,
            already_exists=False,
            message="Канал добавлен в базу как draft и готов к сбору.",
        )

    async def list_channels(self, limit: int = 50, offset: int = 0) -> ChannelListResponse:
        rows, total = await self._channels.list_datasets(limit=limit, offset=offset)
        items: list[ChannelRead] = []
        for r in rows:
            read = ChannelRead.model_validate(r).model_copy(
                update={
                    "extra_conditions": (
                        (r.extras_json or {}).get("dataset_extra_query")
                        if isinstance(r.extras_json, dict)
                        else None
                    )
                }
            )
            items.append(read)
        return ChannelListResponse(total=total, limit=limit, offset=offset, items=items)

    async def delete_channel(self, channel_id: int) -> bool:
        row = await self._channels.get_by_id(channel_id)
        if row is None:
            return False
        await self._channels.delete(row)
        await self._session.commit()
        return True

    async def collect_channel(self, channel_id: int, body: ChannelCollectRequest) -> ChannelCollectResponse:
        topic_pv = (
            body.topic.strip()[:120] + ("…" if len(body.topic.strip()) > 120 else "")
            if isinstance(body.topic, str) and body.topic.strip()
            else None
        )
        logger.info(
            "collect_channel begin channel_id=%s topic_preview=%s channel_ref_provided=%s",
            channel_id,
            topic_pv,
            body.channel_ref is not None,
        )
        row = await self._channels.get_by_id(channel_id)
        if row is None:
            return ChannelCollectResponse(status="not_found", message="Канал не найден", channel_id=channel_id, needs_review=True, reason="Канал не найден")
        if self._intelligence is None or self._coordinator is None:
            msg = "Сервис обновления недоступен"
            await self._record_collect_error_audit(
                channel_id=channel_id,
                row=row,
                body=body,
                status="failed_internal",
                error_text=msg,
                http_code=500,
            )
            return ChannelCollectResponse(status="failed_internal", message=msg, channel_id=channel_id, needs_review=True, reason="Orchestration недоступен")

        entered_ref = (
            self._normalize_channel_ref(body.channel_ref or "")
            if body.channel_ref is not None
            else self._normalize_channel_ref(row.username or "")
        )
        original_topic = (row.topic_search or row.primary_topic or "all").strip() or "all"
        entered_topic = (body.topic or "").strip() if body.topic is not None else original_topic
        entered_extra = (
            body.extra_conditions.strip()
            if body.extra_conditions is not None
            else (
                (row.extras_json or {}).get("dataset_extra_query")
                if isinstance(row.extras_json, dict)
                else None
            )
        )
        created_new_channel = False
        original_username = row.username or ""
        if entered_ref and entered_ref != original_username:
            existing = await self._channels.get_by_username(entered_ref)
            if existing is None:
                new_channel = Channel(
                    telegram_id=self._synthetic_telegram_id(entered_ref),
                    username=entered_ref,
                    title=f"@{entered_ref}",
                    topic_search=original_topic,
                    sync_status="draft",
                    extras_json={"dataset_extra_query": entered_extra},
                )
                await self._channels.add(new_channel)
                await self._session.commit()
                row = new_channel
                channel_id = int(new_channel.id)
                created_new_channel = True
            else:
                row = existing
                channel_id = int(existing.id)

        # Тему можно редактировать для проверки соответствия, но сохраняем исходный topic_search канала.
        req_topic = entered_topic if entered_topic else original_topic
        search_req = SearchChannelsRequest(
            topic=req_topic,
            count=1,
            search_source="telegram_live",
            live_channel_mode="saved",
            selected_channel_ids=[channel_id],
            username_query=f"@{entered_ref}" if entered_ref else (f"@{row.username}" if row.username else None),
            language="ru",
            extra_conditions=entered_extra,
        )
        try:
            res = await self._intelligence.search_channels(body=search_req)
        except Exception as exc:  # noqa: BLE001
            msg = f"Ошибка внешнего сервиса/запроса: {exc}"
            logger.exception("collect_channel upstream failure channel_id=%s", channel_id)
            await self._record_collect_error_audit(
                channel_id=channel_id,
                row=row,
                body=body,
                status="failed_upstream",
                error_text=msg,
                http_code=502,
            )
            return ChannelCollectResponse(
                status="failed_upstream",
                message=msg,
                channel_id=channel_id,
                needs_review=True,
                reason="Ошибка внешнего сервиса/запроса",
            )
        # restore stable topic keyword
        row.topic_search = original_topic
        row.sync_status = "collecting" if res.background_job else row.sync_status
        if isinstance(row.extras_json, dict):
            row.extras_json["dataset_extra_query"] = entered_extra
        else:
            row.extras_json = {"dataset_extra_query": entered_extra}
        await self._session.commit()

        if res.manual_review and res.manual_review.needs_review:
            logger.info(
                "collect_channel end status=needs_review channel_id=%s reason_preview=%s",
                channel_id,
                (res.manual_review.reason or "")[:160],
            )
            return ChannelCollectResponse(
                status="needs_review",
                message="Нужна ручная проверка запроса/канала",
                channel_id=channel_id,
                needs_review=True,
                reason=res.manual_review.reason,
                hints=res.manual_review.hints,
            )
        out = ChannelCollectResponse(
            status="queued" if res.background_job else "ok",
            message="Сбор канала запущен",
            channel_id=channel_id,
            background_job_id=res.background_job.job_id if res.background_job else None,
            created_new_channel=created_new_channel,
        )
        logger.info(
            "collect_channel end channel_id=%s status=%s job_id=%s created_new_channel=%s",
            channel_id,
            out.status,
            out.background_job_id,
            created_new_channel,
        )
        return out
