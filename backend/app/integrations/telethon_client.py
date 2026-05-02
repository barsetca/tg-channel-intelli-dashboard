"""Telethon factory — session lifecycle; actual sync calls run via asyncio.to_thread."""

from telethon import TelegramClient

from app.core.config import settings


class TelethonFactory:
    def __init__(self) -> None:
        self._session = settings.telegram_session_name
        self._api_id = settings.telegram_api_id
        self._api_hash = settings.telegram_api_hash

    def build_client(self) -> TelegramClient | None:
        if not self._api_id or not self._api_hash:
            return None
        return TelegramClient(self._session, self._api_id, self._api_hash)
