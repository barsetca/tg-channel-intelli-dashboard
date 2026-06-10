"""Структуры данных ответов Telethon-сервиса (совместимо с сериализацией для FastAPI / JSON)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TelegramSearchHit(BaseModel):
    """Краткая запись о канале из глобального поиска (contacts.Search)."""

    model_config = ConfigDict(from_attributes=True)

    telegram_channel_id: int = Field(description="Числовой id канала в Telegram (-100 ссылке соответствует id слоя)")
    username: str | None = Field(default=None, description="Публичный @username без @")
    title: str | None = None
    is_broadcast: bool = Field(description="Broadcast-канал (не супергруппа)")
    is_megagroup: bool = Field(default=False, description="True если это мегагруппа (обычно не показываем как «канал»)")


class TelegramChannelFullInfo(BaseModel):
    """Расширенное описание канала после GetFullChannel (ограниченно тем, что нужно приложению)."""

    telegram_channel_id: int
    username: str | None = None
    title: str | None = None
    about: str | None = Field(default=None, description="Описание из настроек канала")
    participants_count: int | None = Field(
        default=None,
        description="Число подписчиков, если передано Telegram (может быть None для приватных/ограниченных случаев)",
    )
    is_broadcast: bool = True
    created_at_utc: datetime | None = Field(
        default=None,
        description="Channel.date из MTProto; в отчёте сравнивается с датой постов (берётся более ранняя)",
    )


class PublishableChannelBrief(BaseModel):
    """Канал, в который текущая сессия может публиковать посты."""

    telegram_channel_id: int
    username: str | None = None
    title: str | None = None
    is_broadcast: bool = True


class TelegramPublishResult(BaseModel):
    telegram_message_id: int
    peer_ref: str
    published_at_utc: datetime
    had_image: bool
    had_text: bool
    had_media: bool = False


class TelegramPostBrief(BaseModel):
    """Контент сообщения канала без сырого MTProto («плоский» DTO под БД/UI)."""

    telegram_message_id: int
    date_utc: datetime
    text: str | None = None
    views: int | None = None
    forwards: int | None = Field(default=None, description="Репостов, если есть в сообщении")
