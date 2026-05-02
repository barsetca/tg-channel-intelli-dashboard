"""
Асинхронный сервис доступа к Telegram по **пользовательской сессии** (Telethon).

Важные условия production:
• Первый вход (код по SMS / пароль 2FA) **интерактивный** и не выполняется внутри этого класса автоматически:
  нужно один раз авторизоваться CLI-скриптом или утилитой и получить файл ``*.session``.
• Все методы считаются **блокирующими по смыслу I/O Telegram** и вызываются только из asyncio-контекста.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel, Message

from app.core.config import Settings, get_settings
from app.integrations.telethon.dto import TelegramChannelFullInfo, TelegramPostBrief, TelegramSearchHit
from app.integrations.telethon.exceptions import (
    TelegramAuthRequiredError,
    TelegramConfigurationError,
    TelegramInvalidIdentifierError,
    TelegramPrivateChannelError,
    TelegramTelethonError,
    coerce_to_telegram_error,
    map_telethon_error,
)
from app.integrations.telethon.rate_limit import run_with_optional_flood_retry

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _normalize_utc(dt: datetime | None) -> datetime | None:
    """Telethon часто отдаёт «наивные» UTC даты — фиксируем для JSON Schema."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TelethonUserSessionService:
    """
    Инкапсулирует ``TelegramClient`` и доменные операции:
    поиск каналов, метаданные, последние посты с учётом FloodWait.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: TelegramClient | None = None
        self._session_path: Path | None = None

    # --- Жизненный цикл клиента -------------------------------------------------

    def is_configured(self) -> bool:
        """Проверяет наличие ``api_id`` / ``api_hash`` в настройках (без создания клиента на диске)."""
        return bool(self._settings.telegram_api_id and self._settings.telegram_api_hash)

    @property
    def connected(self) -> bool:
        """True если ``connect()`` успешно открыл сокет."""
        return self._client is not None and self._client.is_connected()

    async def connect(self) -> None:
        """
        Создаёт клиента, сохраняет сессию в ``telegram_session_dir``, подключается к Telegram.
        Не авторизует пользователя интерактивно — при пустой сессии кидает ``TelegramAuthRequiredError``.
        """
        if not self.is_configured():
            raise TelegramConfigurationError("Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в окружении.")

        api_id = int(self._settings.telegram_api_id or 0)
        api_hash = str(self._settings.telegram_api_hash or "")
        session_dir = Path(self._settings.telegram_session_dir).expanduser().resolve()
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / self._settings.telegram_session_name
        self._session_path = session_file

        # Telethon сам добавляет суффикс .session к переданному пути
        self._client = TelegramClient(str(session_file), api_id, api_hash)
        await self._client.connect()
        if not await self._client.is_user_authorized():
            await self.disconnect()
            raise TelegramAuthRequiredError(
                "Сессия не авторизована. Локально выполните первый вход (telethon строка авторизации / "
                "отдельный скрипт) и положите .session файл в "
                f"{session_dir}",
            )

        logger.info("Telethon: пользователь авторизован, сессия %s", session_file)

    async def disconnect(self) -> None:
        """Аккуратное закрытие клиента при остановке приложения."""
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            logger.debug("Telethon: disconnected")
        self._client = None

    async def startup_for_fastapi(self) -> bool:
        """
        Сценарий lifespan FastAPI: не валить приложение, если Telegram выключен или сессии нет.
        Возвращает True только при полном успехе connect().
        """
        if not self.is_configured():
            logger.info("Telethon: переменные API не заданы — клиент Telegram отключён")
            return False
        try:
            await self.connect()
            return True
        except TelegramAuthRequiredError as exc:
            logger.warning("Telethon: приложение без живой пользовательской сессии (%s)", exc)
        except TelegramConfigurationError:
            logger.exception("Telethon: ошибка конфигурации")
        except Exception as exc:
            logger.exception("Telethon: не удалось подключиться: %s", exc)
        return False

    def _ensure_client_ready(self) -> TelegramClient:
        if self._client is None or not self._client.is_connected():
            raise TelegramTelethonError("Telegram клиент недоступен. Проверьте lifespan приложения или connect().")
        return self._client

    async def _guarded_call(self, label: str, factory: Callable[[], T | Awaitable[T]]) -> T:
        """Оборачивает вызов с повтором при FloodWait (см. ``rate_limit``)."""
        self._ensure_client_ready()

        async def op_wrapper() -> T:
            maybe = factory()
            if hasattr(maybe, "__await__"):
                return await maybe  # type: ignore[no-any-return,no-unused-ignore]
            return maybe  # type: ignore[no-any-return]

        return await run_with_optional_flood_retry(
            op_wrapper,
            max_additional_attempts=max(0, self._settings.telegram_flood_retry_attempts),
            cap_sleep_seconds=max(1, self._settings.telegram_flood_max_wait_seconds),
            operation_label=label,
        )

    # --- Публичные доменные операции -------------------------------------------

    async def search_public_channels(
        self,
        query: str,
        *,
        limit: int = 15,
        broadcast_only: bool = True,
    ) -> list[TelegramSearchHit]:
        """
        Глобальный поиск каналов/чатов (``contacts.Search``).
        По умолчанию отфильтровываются мегагруппы (`broadcast_only=True`).
        """
        q = query.strip()
        if not q:
            raise TelegramInvalidIdentifierError("Пустой текст поиска Telegram.")

        capped = max(1, min(limit, 50))

        async def _search_rpc():
            cli = self._ensure_client_ready()
            return await cli(SearchRequest(q=q, limit=capped))

        raw = await self._guarded_call("contacts.Search", lambda: _search_rpc())
        hits: list[TelegramSearchHit] = []
        # ``chats`` — это объекты каналов и чатов, ``users`` — участники (можно использовать для связей)
        for obj in getattr(raw, "chats", []):
            if not isinstance(obj, Channel):
                continue
            ch: Channel = obj
            if broadcast_only and getattr(ch, "megagroup", False):
                continue
            hits.append(
                TelegramSearchHit(
                    telegram_channel_id=int(ch.id),
                    username=getattr(ch, "username", None),
                    title=getattr(ch, "title", None),
                    is_broadcast=bool(getattr(ch, "broadcast", False)),
                    is_megagroup=bool(getattr(ch, "megagroup", False)),
                )
            )
        return hits

    async def resolve_channel(self, identifier: str | int) -> Channel:
        """
        Превращает строку (@name, полная ссылка, числовой id) в ``Channel``.
        """
        cli = self._ensure_client_ready()
        handle = identifier
        if isinstance(handle, str):
            handle = handle.strip()
            if handle.startswith("https://t.me/"):
                handle = handle.replace("https://t.me/", "").split("/")[0].lstrip("@")
            elif handle.startswith("t.me/"):
                handle = handle.replace("t.me/", "").split("/")[0].lstrip("@")
            else:
                handle = handle.lstrip("@")

        try:
            ent = await self._guarded_call("get_entity", lambda: cli.get_entity(handle))
        except RPCError as exc:
            mapped = map_telethon_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise coerce_to_telegram_error(exc, fallback_message="Ошибка RPC при resolve канала") from exc
        except ValueError as exc:
            raise TelegramInvalidIdentifierError(str(exc)) from exc

        if isinstance(ent, Channel):
            if getattr(ent, "left", False):
                raise TelegramPrivateChannelError("Канал отмечен как left/private для этой сессии.")
            return ent

        raise TelegramInvalidIdentifierError(
            "Сущность не является каналом (найден пользователь или чат). "
            "Проверьте идентификатор или scope.",
        )

    async def get_channel_info(self, identifier: str | int) -> TelegramChannelFullInfo:
        """
        Карточка канала через ``GetFullChannel`` (участники, описание).
        Не включаем сырой access_hash во внешний DTO.
        """
        ch = await self.resolve_channel(identifier)
        cli = self._ensure_client_ready()
        # MTProto принимает TypeInputChannel; «сырой» Channel из get_entity недостаточен — нужен Peer слой Telethon.
        input_ch = await self._guarded_call(
            "get_input_entity",
            lambda: cli.get_input_entity(ch),
        )
        full = await self._guarded_call(
            "GetFullChannelRequest",
            lambda: cli(GetFullChannelRequest(channel=input_ch)),
        )
        fc = getattr(full, "full_chat", None)
        about = getattr(fc, "about", None)
        subs = getattr(fc, "participants_count", None)

        return TelegramChannelFullInfo(
            telegram_channel_id=int(ch.id),
            username=getattr(ch, "username", None),
            title=getattr(ch, "title", None),
            about=str(about) if about else None,
            participants_count=int(subs) if subs is not None else None,
            is_broadcast=bool(getattr(ch, "broadcast", False)),
        )

    async def fetch_recent_posts(
        self,
        identifier: str | int,
        *,
        limit: int = 25,
        max_additional_fetch_rounds_for_flood: int = 0,
    ) -> list[TelegramPostBrief]:
        """
        Возвращает последние N сообщений канала в **хронологическом порядке** (старые сообщения первыми).

        ``get_messages`` отдаёт пакет; при ошибках транспорта срабатывает FloodWait-слой.
        Аргумент ``max_additional_fetch_rounds_for_flood`` зарезервирован под будущий paging/streaming.
        """
        _ = max_additional_fetch_rounds_for_flood
        entity = await self.resolve_channel(identifier)
        cli = self._ensure_client_ready()
        capped = max(1, min(limit, 100))

        async def _get_msgs():
            return await cli.get_messages(entity, limit=capped)

        msgs = await self._guarded_call("get_messages", lambda: _get_msgs())
        material = (
            msg
            for msg in msgs or []
            if isinstance(msg, Message) and getattr(msg, "date", None) is not None
            and getattr(msg, "action", None) is None  # отбросить системные сообщения (присоединение и т.п.)
        )
        ordered = sorted(material, key=lambda m: (m.date, m.id))
        return [self._msg_to_brief(m) for m in ordered]

    @staticmethod
    def _msg_to_brief(msg: Message) -> TelegramPostBrief:
        text = getattr(msg, "message", None) or None
        vid = int(getattr(msg, "id", 0))
        dt_raw = getattr(msg, "date", None)
        if dt_raw is None:
            dt = datetime.now(timezone.utc)
        else:
            dt_norm = _normalize_utc(dt_raw)
            dt = dt_norm or datetime.now(timezone.utc)
        return TelegramPostBrief(
            telegram_message_id=vid,
            date_utc=dt,
            text=text,
            views=getattr(msg, "views", None),
            forwards=getattr(msg, "forwards", None),
        )
