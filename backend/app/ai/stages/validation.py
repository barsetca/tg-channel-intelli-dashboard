"""
Стадия 2: Validation Layer — сначала детерминированные правила.
LLM-gate в архитектуре опционален; здесь оставлен флаг `use_llm_gate` для расширения.
"""

from __future__ import annotations

from app.ai.schemas.context import ContextBundle
from app.ai.schemas.plan import Plan
from app.ai.schemas.validation import ValidationResult, ValidationStatus


def run_validation(*, plan: Plan, bundle: ContextBundle) -> ValidationResult:
    """Правила без LLM: пустой канал, запрос RAG без реализации (предупреждение)."""
    reasons: list[str] = []

    if bundle.post_count == 0:
        return ValidationResult(
            status=ValidationStatus.BLOCK,
            reasons=["Нет постов в выборке — анализ невозможен."],
        )

    if bundle.post_count < 3:
        reasons.append("Мало постов (<3) — выводы будут менее устойчивыми.")

    if plan.use_rag and not bundle.rag_snippets:
        reasons.append(
            "План запрашивает RAG (use_rag=true), но фрагменты retrieval не переданы — "
            "продолжаем без семантического расширения контекста.",
        )

    if reasons:
        return ValidationResult(status=ValidationStatus.WARN, reasons=reasons)

    return ValidationResult(status=ValidationStatus.PASS, reasons=[])
