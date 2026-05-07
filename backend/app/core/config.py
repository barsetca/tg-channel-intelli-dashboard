from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/app.db",
        validation_alias="DATABASE_URL",
    )

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    # Строка сессии Telethon (StringSession). Имеет меньший приоритет, чем TELEGRAM_SESSION в окружении в рантайме.
    telegram_session: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TELEGRAM_SESSION", "telegram_session"),
        description="StringSession; если пусто — используется файл в telegram_session_dir",
    )
    telegram_session_name: str = "telegram_session"
    # Директория для TelegramClient (*.session относительно cwd backend или абсолютный путь)
    telegram_session_dir: str = "data/sessions"
    # Макс. секунд ожидания при одном FloodWait (если Telegram вернёт больше — ждём min).
    telegram_flood_max_wait_seconds: int = 60
    # Число повторов операции после FloodWait (не считая первый вызов)
    telegram_flood_retry_attempts: int = 2
    # Разрешить HTTP-эндпоинты первого входа (телефон → код → 2FA). В production при false — только готовая сессия.
    telegram_interactive_login_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("TELEGRAM_INTERACTIVE_LOGIN", "telegram_interactive_login_enabled"),
    )

    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "channel_messages"

    # Макс. символов на чанк перед эмбеддингом (грубая защита лимита токенов модели).
    embedding_max_chunk_chars: int = 12000
    # Размерность вектора (1536 для text-embedding-3-small). 0 — не проверять после API.
    openai_embedding_dimensions: int = 1536

    @field_validator("telegram_api_id", mode="before")
    @classmethod
    def empty_str_to_none_int(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite+aiosqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url.removeprefix(prefix))
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
