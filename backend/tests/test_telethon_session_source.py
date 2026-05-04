"""Тесты выбора строки сессии Telethon (TELEGRAM_SESSION vs settings)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.integrations.telethon.session_source import (
    effective_string_session,
    persist_string_session_sidecar,
    read_telegram_session_from_os_environ,
    unlink_telethon_sqlite_session_files,
)


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {
        "telegram_api_id": 1,
        "telegram_api_hash": "h",
        "database_url": "sqlite+aiosqlite:///./tests.db",
    }
    base.update(kw)
    return Settings(**base)  # type: ignore[arg-type]


def test_effective_string_prefers_env_over_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_SESSION", "  env_sess  ")
    s = _settings(telegram_session="from_settings")
    assert effective_string_session(s) == "env_sess"


def test_effective_string_falls_back_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_SESSION", raising=False)
    s = _settings(telegram_session="  from_settings ")
    assert effective_string_session(s) == "from_settings"


def test_read_env_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_SESSION", " x ")
    assert read_telegram_session_from_os_environ() == "x"


def test_effective_string_reads_sidecar_after_persist(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("TELEGRAM_SESSION", raising=False)
    d = tmp_path / "sessdir"
    d.mkdir()
    s = _settings(telegram_session_dir=str(d), telegram_session_name="tg", telegram_session=None)
    persist_string_session_sidecar(s, "sidecar_value")
    assert effective_string_session(s) == "sidecar_value"


def test_unlink_removes_session_files(tmp_path) -> None:
    base = tmp_path / "telegram_session"
    sess = tmp_path / "telegram_session.session"
    sess.write_text("sqlite", encoding="utf-8")
    journal = tmp_path / "telegram_session.session-journal"
    journal.write_text("j", encoding="utf-8")
    unlink_telethon_sqlite_session_files(base)
    assert not sess.exists()
    assert not journal.exists()
