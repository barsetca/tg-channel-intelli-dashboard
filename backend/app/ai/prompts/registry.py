"""
Jinja2-шаблоны промптов: `prompts/<bundle>/<name>.j2`.
Версия промпта — в `ContextBundle.prompt_version` и в метаданных анализа.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_PROMPTS_ROOT = Path(__file__).resolve().parent


class PromptRenderer:
    """Рендерит промпты из файловой системы (не из огромных строк в Python)."""

    def __init__(self, root: Path | None = None) -> None:
        root = root or _PROMPTS_ROOT
        # Текстовые шаблоны: autoescape off (не мешать `{` в примерах JSON).
        self._env = Environment(
            loader=FileSystemLoader(str(root)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, relative_path: str, **variables: object) -> str:
        tpl = self._env.get_template(relative_path)
        return tpl.render(**variables)


@lru_cache
def prompt_renderer() -> PromptRenderer:
    return PromptRenderer()
