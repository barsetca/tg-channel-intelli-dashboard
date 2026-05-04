"""Юнит-тесты стадий pipeline без вызова OpenAI."""

from __future__ import annotations

from datetime import datetime, timezone

from app.ai.confidence import aggregate_confidence, signals_from_parts
from app.ai.schemas.plan import Plan
from app.ai.schemas.validation import ValidationResult, ValidationStatus
from app.ai.stages.context_builder import ChannelPipelineInput, PostSnippet, build_context_bundle
from app.ai.stages.validation import run_validation


def test_build_context_and_validation_block_empty_posts() -> None:
    inp = ChannelPipelineInput(
        user_intent="аудит",
        channel_title="T",
        channel_username="t",
        posts=[],
    )
    bundle = build_context_bundle(inp)
    assert bundle.post_count == 0
    plan = Plan()
    v = run_validation(plan=plan, bundle=bundle)
    assert v.status == ValidationStatus.BLOCK


def test_validation_warn_low_posts() -> None:
    posts = [
        PostSnippet(datetime(2025, 1, 1, tzinfo=timezone.utc), "a", views=1),
        PostSnippet(datetime(2025, 1, 2, tzinfo=timezone.utc), "b", views=2),
    ]
    inp = ChannelPipelineInput(
        user_intent="x",
        channel_title=None,
        channel_username=None,
        posts=posts,
    )
    bundle = build_context_bundle(inp)
    plan = Plan(use_rag=True)
    v = run_validation(plan=plan, bundle=bundle)
    assert v.status == ValidationStatus.WARN


def test_aggregate_confidence() -> None:
    s = signals_from_parts(
        data_sufficiency=0.9,
        validation=ValidationResult(status=ValidationStatus.PASS, reasons=[]),
        structured_json_first_try_ok=True,
        plan=Plan(plan_confidence=0.8),
    )
    c = aggregate_confidence(s)
    assert 0.0 < c <= 1.0
