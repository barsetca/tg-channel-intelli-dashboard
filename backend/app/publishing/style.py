"""Загрузка образцов стиля автора для промптов генерации постов."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings

_BUNDLED_STYLE = Path(__file__).resolve().parent / "data" / "author_style_samples.txt"
_REPO_CONTEXT_STYLE = (
    Path(__file__).resolve().parents[3] / "context" / "post_style.txt"
)


def resolve_style_samples_path(settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    custom = (cfg.publishing_style_path or "").strip()
    if custom:
        p = Path(custom).expanduser()
        if p.is_file():
            return p
    if _REPO_CONTEXT_STYLE.is_file():
        return _REPO_CONTEXT_STYLE
    return _BUNDLED_STYLE


@lru_cache(maxsize=1)
def load_author_style_samples() -> str:
    path = resolve_style_samples_path()
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise FileNotFoundError(f"Файл стиля автора пуст: {path}")
    return text
