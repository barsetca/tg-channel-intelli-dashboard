"""Приведение datetime к timezone-aware UTC (SQLite / Telethon отдают разные варианты)."""

from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc_aware(dt: datetime) -> datetime:
    """Наивное время считаем UTC; иначе приводим к UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
