"""Тела запросов для интерактивного входа Telethon (HTTP)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TelegramAuthStartBody(BaseModel):
    """Шаг 1: запрос кода на телефон."""

    phone: str = Field(..., min_length=8, max_length=32, description="E.164 с +, например +79991234567")


class TelegramAuthCodeBody(BaseModel):
    """Шаг 2: код из SMS / Telegram."""

    flow_id: str = Field(..., min_length=8, max_length=256)
    code: str = Field(..., min_length=1, max_length=16, description="Код подтверждения")


class TelegramAuthPasswordBody(BaseModel):
    """Шаг 3 (если включена 2FA): пароль облачного пароля Telegram."""

    flow_id: str = Field(..., min_length=8, max_length=256)
    password: str = Field(..., min_length=1, max_length=256)
