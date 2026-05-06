"""Слияние планировщика с формой пользователя."""

from app.ai.schemas.search_planner import SearchPlannerOutput
from app.orchestration.discovery_pipeline import _search_query_variants
from app.services.channel_search_planner import merge_planner_with_user_request


def test_merge_respects_user_count_cap() -> None:
    user = {"topic": "x", "count": 10, "channel_type": "all"}
    planner = SearchPlannerOutput(
        search_topic="narrow",
        count=30,
        min_subscribers=None,
        max_subscribers=None,
    )
    m = merge_planner_with_user_request(user, planner)
    assert m["count"] == 10
    assert m["search_topic"] == "narrow"


def test_search_query_variants_dedupes_and_expands() -> None:
    v = _search_query_variants("Путешествия", "travel", None)
    assert "Путешествия" in v
    assert "travel" in v
    assert len(v) == len(set(x.casefold() for x in v))


def test_search_query_variants_strict_adds_band_boost_queries() -> None:
    merged = {"min_subscribers": 5000, "max_subscribers": 10000}
    v = _search_query_variants("Нейросети", "Нейросет", merged)
    assert any(x.startswith("канал ") for x in v)
    assert len(v) >= len(_search_query_variants("Нейросети", "Нейросет", None))
