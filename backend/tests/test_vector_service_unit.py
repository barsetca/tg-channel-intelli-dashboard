"""Юнит-тесты семантического слоя (Qdrant ids, чанкинг) без живого Qdrant/OpenAI."""

import uuid

from app.services.vector_service import (
    chunk_text,
    extras_for_chunked_embedding,
    stable_object_uuid,
    stable_point_id_str,
)


def test_chunk_text_empty() -> None:
    assert chunk_text("", 100) == []
    assert chunk_text("   \n", 100) == []


def test_chunk_text_single_under_limit() -> None:
    assert chunk_text("короткий текст", 100) == ["короткий текст"]


def test_chunk_text_splits_long() -> None:
    body = "абвгд" * 30  # 150 символов
    parts = chunk_text(body, max_chars=40)
    assert len(parts) >= 2
    assert sum(len(p) for p in parts) >= len(body) - 10


def test_stable_object_uuid_deterministic() -> None:
    m = "text-embedding-3-small"
    u1 = stable_object_uuid(embedding_model=m, logical_key="post:42", chunk_index=1)
    u2 = stable_object_uuid(embedding_model=m, logical_key="post:42", chunk_index=1)
    assert u1 == u2
    assert u1 != stable_object_uuid(
        embedding_model="text-embedding-3-small", logical_key="post:42", chunk_index=2
    )


def test_stable_point_id_str_matches_uuid() -> None:
    m = "text-embedding-3-small"
    u = stable_object_uuid(embedding_model=m, logical_key="post:1", chunk_index=0)
    s = stable_point_id_str(embedding_model=m, logical_key="post:1", chunk_index=0)
    assert s == str(u)


def test_extras_for_chunked_embedding() -> None:
    d = extras_for_chunked_embedding(all_point_ids=["a", "b"])
    assert d["qdrant_all_chunk_point_ids"] == ["a", "b"]


def test_stable_object_uuid_is_uuid5() -> None:
    u = stable_object_uuid(embedding_model="m", logical_key="k", chunk_index=0)
    expected = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "tg-intel/qdrant/v1|m|k|c0",
    )
    assert u == expected
