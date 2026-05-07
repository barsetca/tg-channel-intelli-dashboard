"""
Выбор строки сессии Telethon (StringSession) для MTProto.

Приоритет для ``StringSession``: переменная окружения ``TELEGRAM_SESSION`` (можно обновить без перезапуска),
затем поле настроек ``telegram_session``, затем sidecar-файл ``{TELEGRAM_SESSION_NAME}.session.string``
в ``TELEGRAM_SESSION_DIR`` (пишется после успешного входа через ``/api/v1/telegram/auth/*``).
Если ни одна строка не найдена — используется файловая SQLite-сессия Telethon в том же каталоге.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


def read_telegram_session_from_os_environ() -> str | None:
    """Свежее значение ``TELEGRAM_SESSION`` из окружения (для ротации без перечитывания pydantic-кэша)."""
    raw = os.environ.get("TELEGRAM_SESSION")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def string_session_sidecar_path(settings: Settings) -> Path:
    """Файл с одной строкой StringSession (пишется после успешного интерактивного входа через API)."""
    d = Path(settings.telegram_session_dir).expanduser().resolve()
    return d / f"{settings.telegram_session_name}.session.string"


def read_string_session_sidecar(settings: Settings) -> str | None:
    p = string_session_sidecar_path(settings)
    if not p.is_file():
        return None
    try:
        s = p.read_text(encoding="utf-8").strip()
        return s or None
    except OSError as exc:
        logger.warning("Telethon: cannot read session sidecar %s: %s", p, exc)
        return None


def persist_string_session_sidecar(settings: Settings, session_str: str) -> Path:
    """Сохраняет StringSession в sidecar-файл (UTF-8 одна строка)."""
    p = string_session_sidecar_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(session_str.strip(), encoding="utf-8")
    logger.info("Telethon: wrote StringSession sidecar %s", p)
    return p


def effective_string_session(settings: Settings) -> str | None:
    """
    Итоговая строка для ``StringSession``: env ``TELEGRAM_SESSION``, затем ``Settings.telegram_session``,
    затем sidecar ``*.session.string`` (после логина через API), иначе ``None`` (тогда — файловая SQLite-сессия).
    """
    return (
        read_telegram_session_from_os_environ()
        or (settings.telegram_session or "").strip()
        or read_string_session_sidecar(settings)
        or None
    )


def unlink_telethon_sqlite_session_files(session_base: Path) -> None:
    """
    Удаляет файлы SQLite-сессии Telethon (``*.session`` и ``*-journal``), если они есть.

    ``session_base`` — путь **без** суффикса ``.session`` (как передаётся в ``TelegramClient(str(path))``).
    """
    base = session_base.expanduser().resolve()
    candidates = [
        Path(str(base) + ".session"),
        Path(str(base) + ".session-journal"),
    ]
    for p in candidates:
        try:
            if p.is_file():
                p.unlink()
                logger.info("Telethon: removed stale session file %s", p)
        except OSError as exc:
            logger.warning("Telethon: could not remove %s: %s", p, exc)
