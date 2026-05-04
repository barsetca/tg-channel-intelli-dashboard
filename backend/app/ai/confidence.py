"""
Агрегированный confidence: комбинация фактов о данных, валидации и успеха парсинга JSON.
Self-report планировщика (`plan_confidence`) получает низкий вес — модели часто завышают.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.schemas.plan import Plan
from app.ai.schemas.validation import ValidationResult, ValidationStatus


@dataclass(frozen=True)
class ConfidenceSignals:
    """Сырые сигналы одного прогона — удобно логировать в `result_json`."""

    data_sufficiency: float
    validation_status: ValidationStatus
    structured_json_first_try_ok: bool
    plan_confidence: float


def aggregate_confidence(signals: ConfidenceSignals) -> float:
    """
    Возвращает итог 0..1.
    Веса подобраны консервативно; при необходимости вынести в настройки приложения.
    """
    w_data = 0.35
    w_val = 0.35
    w_parse = 0.25
    w_plan = 0.05

    val_map = {
        ValidationStatus.PASS: 1.0,
        ValidationStatus.WARN: 0.65,
        ValidationStatus.BLOCK: 0.0,
    }
    v = val_map[signals.validation_status]

    parse_ok = 1.0 if signals.structured_json_first_try_ok else 0.4

    raw = (
        w_data * max(0.0, min(1.0, signals.data_sufficiency))
        + w_val * v
        + w_parse * parse_ok
        + w_plan * max(0.0, min(1.0, signals.plan_confidence))
    )
    return max(0.0, min(1.0, raw))


def signals_from_parts(
    *,
    data_sufficiency: float,
    validation: ValidationResult,
    structured_json_first_try_ok: bool,
    plan: Plan,
) -> ConfidenceSignals:
    return ConfidenceSignals(
        data_sufficiency=data_sufficiency,
        validation_status=validation.status,
        structured_json_first_try_ok=structured_json_first_try_ok,
        plan_confidence=plan.plan_confidence,
    )
