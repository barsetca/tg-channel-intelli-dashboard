"""Результат Validation Layer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    """Статус проверки: при `block` pipeline не вызывает дорогие LLM после валидации."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ValidationResult(BaseModel):
    status: ValidationStatus
    reasons: list[str] = Field(default_factory=list)
    use_llm_gate: bool = Field(
        default=False,
        description="Если True — опционально вызвать короткий LLM-gate (в MVP можно игнорировать).",
    )
