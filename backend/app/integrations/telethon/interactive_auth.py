"""
Интерактивный первый вход Telethon через HTTP (телефон → SMS-код → при необходимости пароль 2FA).

Один экземпляр ``TelegramInteractiveAuthFlows`` на приложение (``app.state``): хранит временные
``TelegramClient`` с пустым ``StringSession()`` до завершения ``sign_in``.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from fastapi import FastAPI
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.errors.rpcerrorlist import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneMigrateError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    PhoneNumberUnoccupiedError,
)
from telethon.sessions import StringSession

from app.integrations.telethon.exceptions import (
    TelegramConfigurationError,
    TelegramInvalidIdentifierError,
    TelegramTelethonError,
)
from app.core.config import Settings
from app.integrations.telethon.session_source import (
    persist_string_session_sidecar,
    unlink_telethon_sqlite_session_files,
)

logger = logging.getLogger(__name__)

FLOW_TTL_SEC = 600
_MAX_PARALLEL_FLOWS = 5


@dataclass
class _PendingFlow:
    client: TelegramClient
    phone: str
    phone_code_hash: str
    created_at: float
    awaits_password: bool = False


class TelegramInteractiveAuthFlows:
    """Управление короткоживущими MTProto-клиентами для пошагового входа."""

    def __init__(self) -> None:
        self._flows: dict[str, _PendingFlow] = {}
        self._lock = asyncio.Lock()

    async def dispose_all(self) -> None:
        async with self._lock:
            for fid in list(self._flows.keys()):
                await self._destroy_unlocked(fid)

    async def _destroy_unlocked(self, flow_id: str) -> None:
        p = self._flows.pop(flow_id, None)
        if p is None:
            return
        try:
            if p.client.is_connected():
                await p.client.disconnect()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Telethon auth flow disconnect %s: %s", flow_id, exc)

    async def _purge_stale_unlocked(self) -> None:
        now = time.time()
        for fid, p in list(self._flows.items()):
            if now - p.created_at > FLOW_TTL_SEC:
                await self._destroy_unlocked(fid)

    async def start(self, settings: Settings, *, phone: str) -> str:
        if not settings.telegram_interactive_login_enabled:
            raise TelegramTelethonError("Интерактивный вход отключён (TELEGRAM_INTERACTIVE_LOGIN).")
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise TelegramConfigurationError("Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH.")

        raw = phone.strip().replace(" ", "")
        if not raw.startswith("+"):
            raise TelegramInvalidIdentifierError(
                "Укажите телефон в международном формате с «+», например +79991234567.",
            )

        api_id = int(settings.telegram_api_id)
        api_hash = str(settings.telegram_api_hash)

        async with self._lock:
            await self._purge_stale_unlocked()
            if len(self._flows) >= _MAX_PARALLEL_FLOWS:
                raise TelegramTelethonError(
                    "Слишком много незавершённых попыток входа. Дождитесь истечения или завершите их.",
                )

            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            if await client.is_user_authorized():
                await client.disconnect()
                raise TelegramTelethonError("Клиент уже авторизован — повторный интерактивный вход не нужен.")

            try:
                sent = await client.send_code_request(raw)
            except (
                PhoneNumberInvalidError,
                PhoneNumberBannedError,
                PhoneNumberFloodError,
                PhoneNumberUnoccupiedError,
                PhoneMigrateError,
            ) as exc:
                await client.disconnect()
                raise TelegramInvalidIdentifierError(str(exc) or "Некорректный номер или ограничение Telegram.") from exc
            except FloodWaitError as exc:
                await client.disconnect()
                secs = getattr(exc, "seconds", None)
                raise TelegramTelethonError(
                    f"Telegram попросил подождать перед повторной отправкой кода (FloodWait{secs or ''}).",
                ) from exc

            flow_id = secrets.token_urlsafe(24)
            self._flows[flow_id] = _PendingFlow(
                client=client,
                phone=raw,
                phone_code_hash=sent.phone_code_hash,
                created_at=time.time(),
            )
            logger.info("Telethon interactive auth: code sent, flow_id prefix=%s", flow_id[:8])
            return flow_id

    async def submit_code(
        self,
        settings: Settings,
        *,
        flow_id: str,
        code: str,
        app: FastAPI,
    ) -> dict[str, object]:
        async with self._lock:
            await self._purge_stale_unlocked()
            p = self._flows.get(flow_id)
            if p is None:
                raise TelegramTelethonError("Сессия входа не найдена или истекла. Запросите код заново.")

            code_clean = code.strip()
            if not code_clean:
                raise TelegramInvalidIdentifierError("Введите код из SMS или Telegram.")

            try:
                await p.client.sign_in(p.phone, code_clean, phone_code_hash=p.phone_code_hash)
            except SessionPasswordNeededError:
                p.awaits_password = True
                return {"status": "needs_password", "flow_id": flow_id}
            except PhoneCodeInvalidError as exc:
                raise TelegramInvalidIdentifierError("Неверный код. Проверьте SMS и время жизни кода.") from exc
            except PhoneCodeExpiredError as exc:
                await self._destroy_unlocked(flow_id)
                raise TelegramInvalidIdentifierError("Код истёк. Запросите новый (шаг с телефоном).") from exc
            except FloodWaitError as exc:
                secs = getattr(exc, "seconds", None)
                raise TelegramTelethonError(f"Слишком много попыток. Подождите {secs or 'некоторое'} сек.") from exc

            session_str = StringSession.save(p.client.session)
            await self._destroy_unlocked(flow_id)
            await apply_new_session_and_reconnect_telegram_service(settings, session_str, app=app)
            return {
                "status": "authorized",
                "telegram_session": session_str,
                "hint": "Сохраните telegram_session в секретах/TELEGRAM_SESSION; на диск записан sidecar *.session.string.",
            }

    async def submit_password(
        self,
        settings: Settings,
        *,
        flow_id: str,
        password: str,
        app: FastAPI,
    ) -> dict[str, object]:
        async with self._lock:
            await self._purge_stale_unlocked()
            p = self._flows.get(flow_id)
            if p is None or not p.awaits_password:
                raise TelegramTelethonError("Сначала отправьте код; пароль 2FA запрашивается после верного кода.")

            pwd = password.strip()
            if not pwd:
                raise TelegramInvalidIdentifierError("Введите пароль двухфакторной аутентификации.")

            try:
                await p.client.sign_in(password=pwd)
            except Exception as exc:  # noqa: BLE001
                raise TelegramTelethonError(f"Неверный пароль 2FA или ошибка входа: {exc}") from exc

            session_str = StringSession.save(p.client.session)
            await self._destroy_unlocked(flow_id)
            await apply_new_session_and_reconnect_telegram_service(settings, session_str, app=app)
            return {
                "status": "authorized",
                "telegram_session": session_str,
                "hint": "Сохраните telegram_session в секретах/TELEGRAM_SESSION; на диск записан sidecar *.session.string.",
            }


async def apply_new_session_and_reconnect_telegram_service(
    settings: Settings,
    session_str: str,
    *,
    app: FastAPI | None = None,
    existing_service: TelethonUserSessionService | None = None,
) -> TelethonUserSessionService | None:
    """
    Пишет StringSession в окружение процесса + sidecar, удаляет старый SQLite-session файл,
    пересоздаёт ``TelethonUserSessionService`` и подключается.

    Если передан ``app``, обновляет ``app.state.telegram_service``.
    Иначе только отключает ``existing_service`` и возвращает новый экземпляр (для тестов).
    """
    import os

    from app.integrations.telethon.user_session_service import TelethonUserSessionService

    s = session_str.strip()
    os.environ["TELEGRAM_SESSION"] = s
    persist_string_session_sidecar(settings, s)
    base = Path(settings.telegram_session_dir).expanduser().resolve() / settings.telegram_session_name
    unlink_telethon_sqlite_session_files(base)

    if app is not None:
        old = getattr(app.state, "telegram_service", None)
        if old is not None:
            try:
                await old.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Old telegram service disconnect: %s", exc)
        svc = TelethonUserSessionService(settings)
        ok, fail = await svc.startup_for_fastapi()
        if ok:
            app.state.telegram_service = svc
            app.state.telegram_startup_failure = None
        else:
            try:
                await svc.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.debug("New telegram service disconnect after failed startup: %s", exc)
            app.state.telegram_service = None
            app.state.telegram_startup_failure = fail
        return app.state.telegram_service

    if existing_service is not None:
        try:
            await existing_service.disconnect()
        except Exception as exc:  # noqa: BLE001
            logger.debug("existing_service disconnect: %s", exc)
    svc = TelethonUserSessionService(settings)
    ok, _fail = await svc.startup_for_fastapi()
    if not ok:
        try:
            await svc.disconnect()
        except Exception as exc:  # noqa: BLE001
            logger.debug("svc disconnect after failed startup: %s", exc)
        return None
    return svc
