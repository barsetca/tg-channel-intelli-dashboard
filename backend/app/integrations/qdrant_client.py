"""Qdrant: коллекция, upsert и поиск по вектору (семантический слой)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HasIdCondition,
    MatchValue,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.core.config import Settings, get_settings


def _as_list_vector(vector: Any) -> list[float]:
    """Один именованный вектор или плоский список → list[float]."""
    if isinstance(vector, dict):
        if not vector:
            raise ValueError("Qdrant вернул пустой vector")
        first = next(iter(vector.values()))
        return [float(x) for x in cast(list[float] | tuple[float, ...], first)]
    return [float(x) for x in cast(list[float] | tuple[float, ...], vector)]


class QdrantStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        kwargs: dict[str, Any] = {"url": self._settings.qdrant_url}
        if self._settings.qdrant_api_key:
            kwargs["api_key"] = self._settings.qdrant_api_key
        self._client = AsyncQdrantClient(**kwargs)
        self._collection = self._settings.qdrant_collection_name

    @property
    def collection_name(self) -> str:
        return self._collection

    async def ensure_collection(self, vector_size: int) -> None:
        exists = await self._client.collection_exists(self._collection)
        if not exists:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    async def upsert_vectors(
        self,
        ids: Sequence[int | str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        points = [
            PointStruct(
                id=ids[i],
                vector=vectors[i],
                payload=(payloads[i] if payloads else {}),
            )
            for i in range(len(ids))
        ]
        await self._client.upsert(collection_name=self._collection, points=points)

    async def search(
        self,
        *,
        query_vector: list[float],
        limit: int,
        query_filter: Filter | None = None,
    ) -> list[ScoredPoint]:
        res = await self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(res.points)

    async def retrieve_vector(self, point_id: str) -> list[float]:
        res = await self._client.retrieve(
            collection_name=self._collection,
            ids=[point_id],
            with_vectors=True,
        )
        if not res:
            raise ValueError(f"Точка Qdrant не найдена: {point_id}")
        return _as_list_vector(res[0].vector)

    async def close(self) -> None:
        await self._client.close()


def payload_filter(
    *,
    content_type: str | None = None,
    channel_id: int | None = None,
) -> Filter | None:
    """Фильтр по payload для search (must)."""
    must: list[FieldCondition] = []
    if content_type is not None:
        must.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
    if channel_id is not None:
        must.append(FieldCondition(key="channel_id", match=MatchValue(value=channel_id)))
    if not must:
        return None
    return Filter(must=cast(Any, must))


def recommend_filter(
    *,
    exclude_point_id: str,
    content_type: str | None = None,
) -> Filter:
    """Фильтр для рекомендаций: исключить якорь, опционально по типу контента."""
    must: list[FieldCondition] = []
    if content_type is not None:
        must.append(FieldCondition(key="content_type", match=MatchValue(value=content_type)))
    must_not = [HasIdCondition(has_id=[exclude_point_id])]
    if must:
        return Filter(must=cast(Any, must), must_not=cast(Any, must_not))
    return Filter(must_not=cast(Any, must_not))
