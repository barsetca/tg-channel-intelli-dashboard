"""Тесты REST intelligence API с подменой зависимостей (без Qdrant/OpenAI)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_intelligence_service, get_vector_service
from app.main import app
from app.schemas.intelligence import (
    ManualReviewFlags,
    SearchChannelsRequest,
    SearchChannelsResponse,
    SimilarChannelItem,
    SimilarChannelsResponse,
)
from app.services.vector_service import VectorSearchHit, VectorService


class _StubIntelligenceService:
    """Заглушка IntelligenceService для HTTP-слоя."""

    async def search_channels(self, body: SearchChannelsRequest) -> SearchChannelsResponse:
        if "лучшие каналы" in body.topic.lower():
            return SearchChannelsResponse(
                channels=[],
                manual_review=ManualReviewFlags(
                    needs_review=True,
                    reason="test",
                    hints=["hint"],
                ),
                normalized_filters=body.model_dump(),
            )
        return SearchChannelsResponse(
            channels=[],
            manual_review=None,
            normalized_filters=body.model_dump(),
        )

    async def get_channel_detail(self, channel_id: int) -> Any:
        return None

    async def run_channel_analysis(
        self,
        *,
        channel_id: int,
        user_intent: str,
    ) -> tuple[Any, str | None]:
        return None, "not_found"

    async def summarize_recent_posts(
        self,
        *,
        channel_id: int,
        body: Any,
    ) -> tuple[Any, str | None]:
        return None, "not_found"

    async def compare_channels(self, body: Any) -> Any:
        return None

    async def export_channels_payload(self, *, limit: int = 500) -> list[dict[str, Any]]:
        return [{"id": 1, "telegram_id": 10, "username": "x", "title": "T", "description": None}]

    def channels_to_csv(self, rows: list[dict[str, Any]]) -> str:
        return "id,telegram_id\n1,10\n"

    def channels_to_json_bytes(self, rows: list[dict[str, Any]]) -> bytes:
        import json

        return json.dumps(rows).encode()


class _StubVectorService:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def semantic_search(self, **kwargs: Any) -> list[VectorSearchHit]:
        return [
            VectorSearchHit(
                point_id="p1",
                score=0.9,
                properties={"channel_id": 2, "post_id": 1, "content_type": "post", "text": "hello"},
            ),
        ]


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_intelligence_service] = lambda: _StubIntelligenceService()
    app.dependency_overrides[get_vector_service] = lambda: _StubVectorService()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_search_channels_returns_manual_review(client: TestClient) -> None:
    r = client.post(
        "/api/v1/search-channels",
        json={
            "topic": "лучшие каналы",
            "count": 5,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["manual_review"]["needs_review"] is True
    assert data["channels"] == []


def test_semantic_search_stub(client: TestClient) -> None:
    r = client.post(
        "/api/v1/semantic-search",
        json={"query": "инвестиции", "limit": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["hits"]) == 1
    assert data["hits"][0]["point_id"] == "p1"


def test_export_json(client: TestClient) -> None:
    r = client.get("/api/v1/export?format=json")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")


def test_channel_not_found(client: TestClient) -> None:
    r = client.get("/api/v1/channel/99999")
    assert r.status_code == 404


def test_analyze_not_found(client: TestClient) -> None:
    r = client.post("/api/v1/analyze/99999", json={})
    assert r.status_code == 404


def test_compare_not_found(client: TestClient) -> None:
    r = client.post("/api/v1/channels/compare", json={"channel_ids": [1, 2]})
    assert r.status_code == 404


@pytest.fixture
def client_intel_real_stub_vector() -> TestClient:
    """Рекомендации: нужен IntelligenceService с find_similar_channels."""

    class IntelWithSimilar(_StubIntelligenceService):
        async def find_similar_channels(
            self,
            *,
            seed_channel_id: int,
            vector: VectorService,
            limit: int = 10,
        ):
            item = SimilarChannelItem(
                channel_id=7,
                score=0.5,
                title="Other",
                username="o",
            )
            return (
                SimilarChannelsResponse(
                    seed_channel_id=seed_channel_id,
                    similar=[item],
                ),
                None,
            )

        async def get_channel_detail(self, channel_id: int) -> Any:
            if channel_id == 1:
                from app.schemas.intelligence import ChannelDetail

                return ChannelDetail(
                    id=1,
                    telegram_id=100,
                    username="seed",
                    title="Seed",
                    description=None,
                )
            return None

    app.dependency_overrides[get_intelligence_service] = lambda: IntelWithSimilar()
    app.dependency_overrides[get_vector_service] = lambda: _StubVectorService()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_recommendations_ok(client_intel_real_stub_vector: TestClient) -> None:
    r = client_intel_real_stub_vector.get("/api/v1/recommendations/1")
    assert r.status_code == 200
    assert r.json()["seed_channel_id"] == 1


def test_openapi_contains_routes() -> None:
    with TestClient(app) as c:
        spec = c.get("/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/api/v1/search-channels" in paths
    assert "/api/v1/channel/{channel_id}" in paths
    assert "/api/v1/analyze/{channel_id}" in paths
    assert "/api/v1/semantic-search" in paths
    assert "/api/v1/recommendations/{channel_id}" in paths
    assert "/api/v1/telegram/auth/start" in paths
    assert "/api/v1/telegram/status" in paths
    assert "/api/v1/orchestration/jobs/{job_id}" in paths
