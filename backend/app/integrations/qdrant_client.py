"""Qdrant vector store — collection lifecycle and upsert/search helpers."""

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings


class QdrantStore:
    def __init__(self) -> None:
        kwargs: dict = {"url": settings.qdrant_url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        self._client = AsyncQdrantClient(**kwargs)
        self._collection = settings.qdrant_collection_name

    async def ensure_collection(self, vector_size: int) -> None:
        exists = await self._client.collection_exists(self._collection)
        if not exists:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    async def upsert_vectors(
        self,
        ids: list[int | str],
        vectors: list[list[float]],
        payloads: list[dict] | None = None,
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
