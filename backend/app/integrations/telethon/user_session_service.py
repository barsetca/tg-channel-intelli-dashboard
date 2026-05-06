"""
Асинхронный сервис доступа к Telegram по **пользовательской сессии** (Telethon).

Первый вход (SMS / 2FA) можно выполнить **через HTTP** эндпоинтами ``/api/v1/telegram/auth/*``
(см. ``telegram_auth`` и ``TelegramInteractiveAuthFlows``): клиент приложения передаёт телефон,
затем код, при необходимости — пароль 2FA; после успеха сессия сохраняется (``TELEGRAM_SESSION`` в процессе,
sidecar ``*.session.string``, переподключение ``app.state.telegram_service``).

Альтернатива без HTTP: заранее выдать ``StringSession`` или файл ``*.session`` (см. ``docs/TELEGRAM_TELETHON.md``).

Все методы считаются **блокирующими по смыслу I/O Telegram** и вызываются только из asyncio-контекста.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.errors.rpcerrorlist import (
    AuthKeyDuplicatedError,
    AuthKeyInvalidError,
    AuthKeyUnregisteredError,
    SessionExpiredError,
    SessionRevokedError,
    UserDeactivatedBanError,
    UserDeactivatedError,
)
from telethon.sessions import StringSession
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
from app.integrations.telethon.session_source import (
    effective_string_session,
    unlink_telethon_sqlite_session_files,
)

logger = logging.getLogger(__name__)

# Ошибки MTProto: сессия недействительна / отозвана — пробуем пересобрать клиента (новая TELEGRAM_SESSION в env или файл).
_RECOVERABLE_SESSION_ERRORS: tuple[type[Exception], ...] = (
    AuthKeyUnregisteredError,
    AuthKeyInvalidError,
    AuthKeyDuplicatedError,
    SessionExpiredError,
    SessionRevokedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
)


def _is_recoverable_session_error(exc: BaseException) -> bool:
    return isinstance(exc, _RECOVERABLE_SESSION_ERRORS)

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
        self._file_session_base: Path | None = None
        self._using_string_session: bool = False
        self._last_string_snapshot: str | None = None

    # --- Жизненный цикл клиента -------------------------------------------------

    def is_configured(self) -> bool:
        """Проверяет наличие ``api_id`` / ``api_hash`` в настройках (без создания клиента на диске)."""
        return bool(self._settings.telegram_api_id and self._settings.telegram_api_hash)

    @property
    def connected(self) -> bool:
        """True если ``connect()`` успешно открыл сокет."""
        return self._client is not None and self._client.is_connected()

    def _build_client(self) -> TelegramClient:
        """
        Собирает ``TelegramClient``: приоритет у ``TELEGRAM_SESSION`` / ``telegram_session`` (StringSession),
        иначе — SQLite-файл в ``telegram_session_dir``.
        """
        if not self.is_configured():
            raise TelegramConfigurationError("Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в окружении.")

        api_id = int(self._settings.telegram_api_id or 0)
        api_hash = str(self._settings.telegram_api_hash or "")
        s = effective_string_session(self._settings)
        if s:
            self._using_string_session = True
            self._file_session_base = None
            self._session_path = None
            logger.info("Telethon: using StringSession from TELEGRAM_SESSION / settings")
            return TelegramClient(StringSession(s), api_id, api_hash)

        self._using_string_session = False
        session_dir = Path(self._settings.telegram_session_dir).expanduser().resolve()
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / self._settings.telegram_session_name
        self._session_path = session_file
        self._file_session_base = session_file
        return TelegramClient(str(session_file), api_id, api_hash)

    async def connect(self) -> None:
        """
        Поднимает MTProto-клиент. Сессия: ``TELEGRAM_SESSION`` (строка) если задана, иначе файл в каталоге.

        Без валидной сессии будет ``TelegramAuthRequiredError`` (или пройдите вход через ``/api/v1/telegram/auth/*``).
        """
        if self._client is not None and self._client.is_connected():
            if await self._client.is_user_authorized():
                return
            await self.disconnect()

        self._client = self._build_client()
        try:
            await self._client.connect()
        except Exception:
            await self.disconnect()
            raise

        if not await self._client.is_user_authorized():
            await self.disconnect()
            hint = (
                "Сессия не авторизована или ключ отозван. Задайте актуальную переменную TELEGRAM_SESSION "
                "(StringSession из рабочего клиента Telethon) либо выполните первый вход и положите .session в "
                f"{Path(self._settings.telegram_session_dir).expanduser().resolve()}."
            )
            raise TelegramAuthRequiredError(hint)

        if self._using_string_session:
            logger.info("Telethon: пользователь авторизован (StringSession)")
        else:
            logger.info("Telethon: пользователь авторизован, файл сессии %s", self._session_path)
        self._last_string_snapshot = effective_string_session(self._settings) if self._using_string_session else None

    async def ensure_session_for_api(self) -> None:
        """
        Перед обращением к Telegram API: при необходимости установить соединение и валидную сессию.

        Если задан ``TELEGRAM_SESSION`` (StringSession) и строка в окружении **изменилась** после последнего
        успешного ``connect()``, клиент пересобирается (актуально для ротации секрета без рестарта процесса).
        """
        if not self.is_configured():
            raise TelegramConfigurationError("Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в окружении.")

        want = effective_string_session(self._settings)
        ok = (
            self._client is not None
            and self._client.is_connected()
            and await self._client.is_user_authorized()
        )
        if ok:
            if want and not self._using_string_session:
                logger.info("Telethon: TELEGRAM_SESSION is set — preferring StringSession over file; reconnecting")
                await self.disconnect()
            elif self._using_string_session and want != self._last_string_snapshot:
                logger.info("Telethon: TELEGRAM_SESSION string changed or cleared — reconnecting")
                await self.disconnect()
            else:
                return

        await self.connect()

    async def _recover_invalid_session(self) -> None:
        """После AUTH_KEY_UNREGISTERED / SessionRevoked и т.п.: сброс клиента и при файловой сессии — удаление .session."""
        was_file = not self._using_string_session
        file_base = self._file_session_base
        await self.disconnect()
        if was_file and file_base is not None:
            unlink_telethon_sqlite_session_files(file_base)

    async def disconnect(self) -> None:
        """Аккуратное закрытие клиента при остановке приложения."""
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            logger.debug("Telethon: disconnected")
        self._client = None
        self._using_string_session = False
        self._file_session_base = None
        self._session_path = None
        self._last_string_snapshot = None

    async def startup_for_fastapi(self) -> tuple[bool, str | None]:
        """
        Сценарий lifespan FastAPI: не валить приложение, если Telegram выключен или сессии нет.

        Возвращает ``(True, None)`` при успешном ``connect()``; иначе ``(False, краткая причина для UI/логов)``.
        """
        if not self.is_configured():
            msg = "Не заданы TELEGRAM_API_ID / TELEGRAM_API_HASH."
            logger.info("Telethon: %s — клиент Telegram отключён", msg)
            return False, msg
        try:
            await self.connect()
            return True, None
        except TelegramAuthRequiredError as exc:
            logger.warning("Telethon: приложение без живой пользовательской сессии (%s)", exc)
            return False, str(exc)
        except TelegramConfigurationError:
            logger.exception("Telethon: ошибка конфигурации")
            return False, "Ошибка конфигурации Telethon (см. лог сервера)."
        except Exception as exc:  # noqa: BLE001
            logger.exception("Telethon: не удалось подключиться: %s", exc)
            return False, f"Ошибка подключения Telethon: {exc}"

    def _ensure_client_ready(self) -> TelegramClient:
        if self._client is None or not self._client.is_connected():
            raise TelegramTelethonError("Telegram клиент недоступен. Проверьте lifespan приложения или connect().")
        return self._client

    async def _guarded_call(
        self,
        label: str,
        factory: Callable[[], T | Awaitable[T]],
        *,
        max_additional_attempts: int | None = None,
        cap_sleep_seconds: int | None = None,
    ) -> T:
        """Перед RPC: ``ensure_session_for_api``; FloodWait-ретраи; одна попытка восстановления при «битой» сессии."""
        await self.ensure_session_for_api()
        retry_attempts = (
            max(0, max_additional_attempts)
            if max_additional_attempts is not None
            else max(0, self._settings.telegram_flood_retry_attempts)
        )
        retry_cap_seconds = (
            max(1, cap_sleep_seconds)
            if cap_sleep_seconds is not None
            else max(1, self._settings.telegram_flood_max_wait_seconds)
        )

        async def op_wrapper() -> T:
            maybe = factory()
            if hasattr(maybe, "__await__"):
                return await maybe  # type: ignore[no-any-return,no-unused-ignore]
            return maybe  # type: ignore[no-any-return]

        try:
            return await run_with_optional_flood_retry(
                op_wrapper,
                max_additional_attempts=retry_attempts,
                cap_sleep_seconds=retry_cap_seconds,
                operation_label=label,
            )
        except BaseException as exc:
            if _is_recoverable_session_error(exc):
                logger.warning("Telethon: session error in %s (%s) — recovering", label, type(exc).__name__)
                await self._recover_invalid_session()
                await self.ensure_session_for_api()
                return await run_with_optional_flood_retry(
                    op_wrapper,
                    max_additional_attempts=retry_attempts,
                    cap_sleep_seconds=retry_cap_seconds,
                    operation_label=f"{label} (after session recovery)",
                )
            raise

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

        # MTProto `contacts.Search` обычно допускает до ~100 результатов за один запрос.
        capped = max(1, min(limit, 100))

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
            ent = await self._guarded_call(
                "get_entity",
                lambda: self._ensure_client_ready().get_entity(handle),
                max_additional_attempts=0,
                cap_sleep_seconds=2,
            )
        except RPCError as exc:
            mapped = map_telethon_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise coerce_to_telegram_error(exc, fallback_message="Ошибка RPC при resolve канала") from exc
        except ValueError as exc:
            raise TelegramInvalidIdentifierError(str(exc)) from exc

        if isinstance(ent, Channel):
            # `left=True` не всегда означает приватность: публичный канал с username может быть
            # доступен без вступления. Блокируем только явно недоступные сущности без username.
            if getattr(ent, "left", False) and not getattr(ent, "username", None):
                raise TelegramPrivateChannelError("Канал недоступен для этой сессии (left/private, без публичного username).")
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
        # MTProto принимает TypeInputChannel; «сырой» Channel из get_entity недостаточен — нужен Peer слой Telethon.
        input_ch = await self._guarded_call(
            "get_input_entity",
            lambda: self._ensure_client_ready().get_input_entity(ch),
        )
        full = await self._guarded_call(
            "GetFullChannelRequest",
            lambda: self._ensure_client_ready()(GetFullChannelRequest(channel=input_ch)),
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
        capped = max(1, min(limit, 100))

        async def _get_msgs():
            return await self._ensure_client_ready().get_messages(entity, limit=capped)

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
