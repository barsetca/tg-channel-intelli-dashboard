# Qdrant: семантический слой (embeddings pipeline)

Документ описывает стратегию индексирования и использование `VectorService` + `QdrantStore`.

## Роль в архитектуре

- Одна **коллекция** Qdrant (`qdrant_collection_name`, по умолчанию `channel_messages`).
- Векторы только **внешние** (OpenAI Embeddings API), расстояние **Cosine**.
- Метаданные в **payload**; строки `EmbeddingMetadata` в **реляционной БД приложения** (SQLAlchemy) хранят `qdrant_collection` и `qdrant_point_id` на чанк. По умолчанию в `Settings.database_url` задан **SQLite** (`sqlite+aiosqlite:///./data/app.db`); через `DATABASE_URL` можно подключить PostgreSQL или другой движок, поддерживаемый SQLAlchemy.

## Стратегия индексирования

1. **Чанки** — `chunk_text` с лимитом `embedding_max_chunk_chars`.
2. **Стабильный id точки** — `stable_point_id_str` (UUID5 от модели, логического ключа и индекса чанка) для идемпотентного upsert.
3. **Типы контента** — поле payload `content_type`: `post` | `summary` | `profile`.
4. **Фильтрация** — `channel_id`, `post_id`, `summary_id`, `profile_user_id` в payload; поиск через `FieldCondition` + `Filter`.

## Примеры (Python)

```python
from app.services.vector_service import VectorService, extras_for_chunked_embedding

async def example():
    async with VectorService() as vs:
        ids = await vs.index_post(post_id=1, channel_id=10, text="…")
        extras = extras_for_chunked_embedding(all_point_ids=ids)
        hits = await vs.semantic_search(query="налоги", limit=5, channel_id=10)
        rec = await vs.recommend_similar(point_id=ids[0], limit=5, content_type="post")
```

## Переменные окружения

`QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME`, `EMBEDDING_MAX_CHUNK_CHARS`, `OPENAI_EMBEDDING_DIMENSIONS` (0 — не проверять размерность после API).

## Размерность коллекции

Коллекция создаётся при первой операции с известной длиной вектора (после эмбеддинга). Значение `openai_embedding_dimensions` должно совпадать с моделью, иначе upsert завершится ошибкой несоответствия размеров.
