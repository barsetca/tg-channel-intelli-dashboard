"""
Семантический слой: эмбеддинги OpenAI + Qdrant (cosine), поиск и рекомендации.

Пайплайн:
1) Текст режется на чанки (`chunk_text`, лимит `embedding_max_chunk_chars`).
2) На чанк — `embeddings.create`, точка upsert в Qdrant с payload-метаданными.
3) Поиск: вектор запроса + `search` с опциональным фильтром по payload.
4) Похожие: вектор якорной точки (`retrieve`) + `search` с `must_not` по id якоря.

Связь с SQL: для каждого чанка создавайте строку `EmbeddingMetadata` с `qdrant_collection` и
`qdrant_point_id` (строка id точки). Список id чанков можно дублировать в `extras_json`, см.
`extras_for_chunked_embedding`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from qdrant_client.models import ScoredPoint

from app.core.config import Settings, get_settings
from app.integrations.openai_client import OpenAIClient
from app.integrations.qdrant_client import QdrantStore, payload_filter, recommend_filter

# Тип контента в одной коллекции Qdrant (дискриминация по payload).
ContentType = Literal["post", "summary", "profile"]

_MISSING_INT = -1


def chunk_text(text: str, max_chars: int) -> list[str]:
    """
    Делит длинный текст на чанки по границам абзацев, затем жёстко по длине.

    Эвристика: модели эмбеддингов ограничены по токенам; лимит в символах проще в бэкенде.
    """
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + max_chars, len(cleaned))
        piece = cleaned[start:end]
        if end < len(cleaned):
            cut = piece.rfind("\n\n")
            if cut == -1:
                cut = piece.rfind("\n")
            if cut > max_chars // 4:
                piece = piece[:cut]
                end = start + cut
        chunks.append(piece.strip())
        start = end if end > start else start + max_chars
    return [c for c in chunks if c]


def stable_object_uuid(*, embedding_model: str, logical_key: str, chunk_index: int) -> uuid.UUID:
    """Детерминированный UUID точки Qdrant для идемпотентных upsert."""
    payload = f"tg-intel/qdrant/v1|{embedding_model}|{logical_key}|c{chunk_index}"
    return uuid.uuid5(uuid.NAMESPACE_URL, payload)


def stable_point_id_str(*, embedding_model: str, logical_key: str, chunk_index: int) -> str:
    """Строковый id точки для `qdrant_point_id` и API Qdrant."""
    u = stable_object_uuid(
        embedding_model=embedding_model,
        logical_key=logical_key,
        chunk_index=chunk_index,
    )
    return str(u)


def extras_for_chunked_embedding(*, all_point_ids: list[str]) -> dict[str, Any]:
    """Доп. JSON для `extras_json` при нескольких чанках на один логический объект."""
    return {"qdrant_all_chunk_point_ids": all_point_ids}


@dataclass(frozen=True)
class VectorSearchHit:
    """Один результат семантического поиска или рекомендаций (Qdrant `ScoredPoint`)."""

    point_id: str
    score: float | None
    properties: dict[str, Any]


class VectorService:
    """
    OpenAI embeddings + `QdrantStore`.

    `await connect()` создаёт коллекцию при отсутствии (размерность из настроек или 1536).
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        openai: OpenAIClient | None = None,
        qdrant: QdrantStore | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._openai = openai or OpenAIClient()
        self._qdrant = qdrant or QdrantStore(self._settings)
        self._owns_qdrant = qdrant is None

    async def __aenter__(self) -> VectorService:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Коллекция Qdrant создаётся лениво при первой записи или поиске (по длине вектора)."""
        return None

    async def close(self) -> None:
        if self._owns_qdrant:
            await self._qdrant.close()

    async def ensure_schema(self) -> None:
        """Для Qdrant коллекция создаётся при первой записи или поиске."""
        await self.connect()

    async def _upsert_chunks(
        self,
        *,
        content_type: ContentType,
        logical_key: str,
        texts: Sequence[str],
        base_props: dict[str, Any],
    ) -> list[str]:
        if not texts:
            return []
        model = self._openai.embedding_model
        vectors = await self._openai.embed_texts(list(texts))
        expected = self._settings.openai_embedding_dimensions
        if expected > 0 and len(vectors[0]) != expected:
            got = len(vectors[0])
            raise ValueError(
                f"Размерность эмбеддинга {got} не совпадает с "
                f"openai_embedding_dimensions={expected}"
            )
        dim = len(vectors[0])
        await self._qdrant.ensure_collection(dim)

        ids: list[str] = []
        payloads: list[dict[str, Any]] = []
        for i, text in enumerate(texts):
            pid = stable_point_id_str(
                embedding_model=model,
                logical_key=logical_key,
                chunk_index=i,
            )
            ids.append(pid)
            payloads.append(
                {
                    **base_props,
                    "content_type": content_type,
                    "text": text,
                    "chunk_index": i,
                    "embedding_model": model,
                },
            )
        await self._qdrant.upsert_vectors(ids, vectors, payloads)
        return ids

    async def index_post(self, *, post_id: int, channel_id: int, text: str) -> list[str]:
        """Индексация поста (несколько чанков → несколько точек)."""
        chunks = chunk_text(text, self._settings.embedding_max_chunk_chars)
        return await self._upsert_chunks(
            content_type="post",
            logical_key=f"post:{post_id}",
            texts=chunks,
            base_props={
                "channel_id": channel_id,
                "post_id": post_id,
                "summary_id": _MISSING_INT,
                "profile_user_id": "",
            },
        )

    async def index_summary(self, *, summary_id: int, channel_id: int, text: str) -> list[str]:
        """Индексация саммари."""
        chunks = chunk_text(text, self._settings.embedding_max_chunk_chars)
        return await self._upsert_chunks(
            content_type="summary",
            logical_key=f"summary:{summary_id}",
            texts=chunks,
            base_props={
                "channel_id": channel_id,
                "post_id": _MISSING_INT,
                "summary_id": summary_id,
                "profile_user_id": "",
            },
        )

    async def index_profile(self, *, channel_id: int, user_id: int, text: str) -> list[str]:
        """
        Индексация профиля (bio и т.д. в `text`).

        `user_id` — Telegram user id; в payload как строка.
        """
        chunks = chunk_text(text, self._settings.embedding_max_chunk_chars)
        uid = str(user_id)
        return await self._upsert_chunks(
            content_type="profile",
            logical_key=f"profile:{channel_id}:{uid}",
            texts=chunks,
            base_props={
                "channel_id": channel_id,
                "post_id": _MISSING_INT,
                "summary_id": _MISSING_INT,
                "profile_user_id": uid,
            },
        )

    async def semantic_search(
        self,
        *,
        query: str,
        limit: int = 20,
        content_type: ContentType | None = None,
        channel_id: int | None = None,
    ) -> list[VectorSearchHit]:
        """Семантический поиск: эмбеддинг запроса + Qdrant `search` с фильтром payload."""
        qvec = (await self._openai.embed_texts([query]))[0]
        await self._qdrant.ensure_collection(len(qvec))
        qf = payload_filter(content_type=content_type, channel_id=channel_id)
        points = await self._qdrant.search(query_vector=qvec, limit=limit, query_filter=qf)
        return _hits_from_scored(points)

    async def recommend_similar(
        self,
        *,
        point_id: str,
        limit: int = 10,
        content_type: ContentType | None = None,
    ) -> list[VectorSearchHit]:
        """Рекомендации: вектор точки-якоря + поиск ближайших, якорь исключается фильтром."""
        anchor_vec = await self._qdrant.retrieve_vector(point_id)
        await self._qdrant.ensure_collection(len(anchor_vec))
        qf = recommend_filter(exclude_point_id=point_id, content_type=content_type)
        points = await self._qdrant.search(query_vector=anchor_vec, limit=limit, query_filter=qf)
        return _hits_from_scored(points)


def _hits_from_scored(points: Sequence[ScoredPoint]) -> list[VectorSearchHit]:
    hits: list[VectorSearchHit] = []
    for sp in points:
        pid = str(sp.id)
        props = dict(sp.payload or {})
        hits.append(VectorSearchHit(point_id=pid, score=sp.score, properties=props))
    return hits
