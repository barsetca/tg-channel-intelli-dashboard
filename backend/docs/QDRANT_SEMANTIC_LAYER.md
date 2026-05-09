# Qdrant: семантический слой и эмбеддинги

Документ описывает **текущую** интеграцию с Qdrant в монорепозитории: клиент [`QdrantStore`](../app/integrations/qdrant_client.py), опциональный сервис [**`VectorService`**](../app/services/vector_service.py) и **именованные коллекции**, которые заполняет продуктовая логика (`IntelligenceService`, `discovery_pipeline`).

Подробнее по сценариям см. также [`AI_PIPELINE_ARCHITECTURE.md`](AI_PIPELINE_ARCHITECTURE.md).

---

## 1. Роль в архитектуре

| Компонент | Назначение |
|-----------|------------|
| **`QdrantStore`** | Низкоуровневый async-клиент: создание коллекций, upsert, **`search` / `search_in_collection`** (внутри — `query_points`), **`scroll_in_collection`**, **`retrieve_vector`**; расстояние **Cosine** (`Distance.COSINE`). |
| **`VectorService`** | Уровень приложения над OpenAI Embeddings + **одна коллекция по умолчанию**: чанкинг текста, стабильные id точек, payload с `content_type`. |
| **Именованные коллекции** | Отдельные коллекции для сценариев 3 / 4 / 6 (`telegram_*`), без прохождения через `VectorService` при записи из `IntelligenceService`. |

Эмбеддинги считаются **только через OpenAI** (режим external vectors для Qdrant).

---

## 2. Коллекции: две парадигмы

### 2.1. Коллекция по умолчанию (`channel_messages`)

- Имя из настроек: **`Settings.qdrant_collection_name`** (env: **`QDRANT_COLLECTION_NAME`**, по умолчанию строка **`channel_messages`** в [`config.py`](../app/core/config.py)).
- Используется **`VectorService`**: методы `_upsert_chunks` вызывают `QdrantStore.ensure_collection(dim)` и `upsert_vectors` **без** переименования коллекции.
- Полезно для универсальной индексации постов/сводок/профилей с фильтром по **`content_type`** в payload (`post` \| `summary` \| `profile`) и **`channel_id`**.

### 2.2. Продуктовые коллекции `telegram_*` (явные строки в коде)

| Коллекция | Кто создаёт / заполняет | Кто читает |
|-----------|--------------------------|------------|
| **`telegram_post_summaries`** | Сценарий 3 («резюмировать посты»), `summarize_recent_posts_by_handle` / связанная логика — upsert точек через `upsert_vectors_to` | Сценарий 4 (`semantic_search_scenario4`), сценарий 6 (`find_similar_channels`) |
| **`telegram_channel_windows`** | Сценарий 3 — агрегированное «окно» контента канала в Qdrant | Сценарий 4, сценарий 6 |
| **`telegram_channel_profiles`** | Оркестратор discovery: **`run_vector_stage`** в [`discovery_pipeline.py`](../app/orchestration/discovery_pipeline.py) — эмбеддинг текста из SQLite (`title` / `description` / `primary_topic` / `topic_search`, обрезка до `embedding_max_chunk_chars`); payload-индексы `channel_id`, `entity_type`, `channel_username` | Сценарий 6 (`find_similar_channels`) |

Для **`telegram_post_summaries`** и **`telegram_channel_windows`** индексы создаются в **`_ensure_scenario3_qdrant_schema`**; для **`telegram_channel_profiles`** — в **`run_vector_stage`**.

**Важно:** сценарий 4 **ожидает**, что после сценария 3 в Qdrant есть данные и непустые коллекции иначе ответ может быть **`needs_review`** с подсказкой сначала проиндексировать сводки.

---

## 3. Реализация `QdrantStore` (кратко)

Файл: [`app/integrations/qdrant_client.py`](../app/integrations/qdrant_client.py).

- **`ensure_collection(vector_size)`** — коллекция с именем `settings.qdrant_collection_name`.
- **`ensure_collection_named(name, vector_size)`** — произвольное имя (используется для `telegram_*`).
- **`upsert_vectors` / `upsert_vectors_to`** — запись точек с payload.
- **`search` / `search_in_collection`** — векторный поиск через `query_points`.
- **`scroll_in_collection`** — обход точек с фильтром (используется в похожих каналах для снятия векторов seed-канала).
- **`retrieve_vector`** — вектор по id в **дефолтной** коллекции (типично для `VectorService.recommend_similar`).

Вспомогательные фильтры: **`payload_filter`**, **`recommend_filter`** — для режима одной коллекции с типизированным payload.

После операций во многих эндпоинтах вызывающий код делает **`await qdrant.close()`** (жизненный цикл клиента привязан к запросу/джобу, не держится глобально — см. комментарии в [`deps.py`](../app/api/deps.py)).

---

## 4. `VectorService`: чанки, stable id, SQL-связь

Файл: [`app/services/vector_service.py`](../app/services/vector_service.py).

1. **Чанки** — `chunk_text()`, лимит **`embedding_max_chunk_chars`** из настроек.
2. **Стабильный id точки** — `stable_point_id_str()` → UUID5 (`NAMESPACE_URL`) от строки `tg-intel/qdrant/v1|{embedding_model}|{logical_key}|c{chunk_index}` — идемпотентный upsert.
3. **Проверка размерности** — если **`openai_embedding_dimensions` > 0**, после `embed_texts` сравнивается длина первого вектора с настройкой; иначе расхождение приведёт к `ValueError`.
4. **Тип контента в payload**: `post` \| `summary` \| `profile` + поля `channel_id`, `post_id`, `summary_id`, `profile_user_id` (заглушки см. код `_upsert_chunks`).

### Связь с реляционной БД

Рекомендуемый контракт (для путей через `VectorService`): на каждый записанный чанк поддерживать строку **`EmbeddingMetadata`** ([`embedding_metadata.py`](../app/models/embedding_metadata.py)) с полями `qdrant_collection`, `qdrant_point_id`, `embedding_model`, `chunk_index`, `dims`, опционально `extras_json` (например `extras_for_chunked_embedding`).

**Индексированные сценарии 3/4/6** в **коллекциях `telegram_*`** могут работать без записей в `embeddings_metadata` — источником истины для привязки к каналам служит **payload в Qdrant** (`channel_id`, `channel_username`, `message_id`, …).

---

## 5. Пример: универсальный семантический поиск через `VectorService`

```python
from app.services.vector_service import VectorService, extras_for_chunked_embedding


async def example():
    svc = VectorService()
    await svc.ensure_schema()
    try:
        ids = await svc.index_post(post_id=1, channel_id=10, text="… длинный текст …")
        extras = extras_for_chunked_embedding(all_point_ids=ids)
        # сохраните extras в нужном месте (например extras_json записи EmbeddingMetadata)

        hits = await svc.semantic_search(query="налоги", limit=5, channel_id=10)
        rec = await svc.recommend_similar(point_id=ids[0], limit=5, content_type="post")
        return hits, rec
    finally:
        await svc.close()
```

`GET /api/v1/recommendations/{channel_id}` (похожие каналы, сценарий 6) **инъецирует** `VectorService`, но **`find_similar_channels` в коде удаляет ссылку на него (`del vector`)** и собирает кандидатов через **`QdrantStore` и коллекции `telegram_*`** (плюс fallback по каталогу). `VectorService` остаётся в DI для возможного переиспользования и симметрии зависимостей.

---

## 6. Переменные окружения и настройки

| Переменная / поле Settings | Назначение |
|----------------------------|------------|
| **`QDRANT_URL`** | HTTP API Qdrant (`Settings.qdrant_url`; Docker: например `http://qdrant:6333`, локально `http://localhost:6333`). Часть имён задаётся в [`.env.example`](../../.env.example). |
| **`QDRANT_API_KEY`** | Необязательно для локального образа без auth. |
| **`QDRANT_COLLECTION_NAME`** → `qdrant_collection_name` | Имя коллекции для **`VectorService`** (по умолчанию `channel_messages`). |
| **`OPENAI_API_KEY`** | Нужен для эмбеддингов. |
| **`OPENAI_EMBEDDING_MODEL`** (`openai_embedding_model`) | Модель эмбеддингов, например `text-embedding-3-small`. |
| **`OPENAI_EMBEDDING_DIMENSIONS`** (`openai_embedding_dimensions`) | Ожидаемая размерность (по умолчанию `1536`); **`0`** — не проверять размер после ответа API. |
| **`EMBEDDING_MAX_CHUNK_CHARS`** (`embedding_max_chunk_chars`) | Макс. длина чанка в символах для `VectorService` / обрезка текста перед эмбеддингом в части сценариев. |

Рекомендация для production: указать **`openai_embedding_dimensions`**, совпадающую с выбранной embedding-моделью, чтобы ловить несостыковку размеров коллекции и векторов до падения upsert на стороне Qdrant.

---

## 7. Создание коллекций и размерность

- Для **`VectorService`**: коллекция создаётся при первом upsert или поиске с известным `dim = len(vector[0])`.
- Для **`telegram_*`**: `ensure_collection_named` после получения первого вектора от OpenAI для данного пайплайна.

Расхождение размерности вектора и объявленной при `create_collection` приводит к ошибке со стороны Qdrant.

---

## 8. Краткий чеклист для разработчика

- Нужна **универсальная** индексация поста/саммари в одну коллекцию с фильтрами → **`VectorService`** + **`EmbeddingMetadata`**.
- Нужны **семантический поиск по сводкам** и **похожие каналы как в продукте** → держите в актуальном состоянии **`telegram_post_summaries`**, **`telegram_channel_windows`**, **`telegram_channel_profiles`** и индексные payload-поля.
- После изменения имени модели эмбеддингов переиндексируйте точки или используйте новые коллекции/префиксы id, чтобы не смешивать разные размерности в одной коллекции.
