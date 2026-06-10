# Backend API

Общее описание продукта, стек и полная инструкция по запуску монорепозитория (включая Docker и фронтенд): [README в корне репозитория](../README.md).

## Локальный запуск только backend

Установка:

```bash
pip install -e ".[dev]"
```

или [uv](https://docs.astral.sh/uv/): `uv pip install -e ".[dev]"`.

Из каталога `backend/`: скопируйте переменные из корня (`cp ../.env.example ../.env`), затем миграции и сервер:

```bash
PYTHONPATH=. python3 -m alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Убедитесь, что файл `.env` находится в корне репозитория (или задайте переменные окружения вручную).

Доменные ORM-модели и связи описаны в пакете `app/models/`; обзор схемы, миграций и советы по масштабированию — в [README репозитория](../README.md#схема-данных-sqlite-orm).

Метрики каналов (формулы, входные поля): [docs/CHANNEL_METRICS.md](docs/CHANNEL_METRICS.md).

Архитектура AI pipeline (оркестратор, интеллект, Qdrant): [docs/AI_PIPELINE_ARCHITECTURE.md](docs/AI_PIPELINE_ARCHITECTURE.md).

Qdrant и эмбеддинги (`VectorService`, коллекции `telegram_*`): [docs/QDRANT_SEMANTIC_LAYER.md](docs/QDRANT_SEMANTIC_LAYER.md).

Telethon (user session, FloodWait, HTTP-вход): [docs/TELEGRAM_TELETHON.md](docs/TELEGRAM_TELETHON.md).

Публикация в Telegram (OpenAI + Telethon, предпросмотр, env): [docs/PUBLISHING.md](docs/PUBLISHING.md).

## REST API v1

Префикс приложения **`/api/v1`**. После запуска: Swagger **`/docs`**, ReDoc **`/redoc`** (корень приложения без префикса v1 для UI).

Монтирование роутов: [`app/api/v1/router.py`](app/api/v1/router.py). Фоновый пайплайн discovery/live: модуль **`app/orchestration/`** (`coordinator.py`, `discovery_pipeline.py`).

### Сценарии из `context/user_scenario.txt`

| Метод | Путь (после `/api/v1`) | Назначение |
|-------|-------------------------|------------|
| `POST` | `/search-channels` | **1**, **8**: `saved_catalog` (SQLite) или `telegram_live` (фон + `job_id` при необходимости); ответ может содержать `manual_review` |
| `GET` | `/search-channels/topics` | Справочник ниш из `channels.topic_search` |
| `GET` | `/orchestration/jobs/{job_id}` | Статус фона после `telegram_live` |
| `POST` | `/orchestration/jobs/{job_id}/cancel` | Отмена задания |
| `POST` | `/ai/plan_and_collect` | Planner / review JSON без запуска фактического сбора данных |
| `GET` | `/telegram/status` | UI: ключи Telegram, готовность сессии, флаги интерактивного входа ([`telegram_auth`](app/api/v1/endpoints/telegram_auth.py)) |
| `POST` | `/telegram/auth/start`, `/telegram/auth/code`, `/telegram/auth/password` | Первый вход Telethon (при **`TELEGRAM_INTERACTIVE_LOGIN`**) |
| `GET` | `/channel/{channel_id}` | **2** — карточка канала из БД |
| `POST` | `/channel/{channel_id}/summarize` | **3** — сводка по постам канала уже в каталоге (SQLite + Telethon при необходимости) |
| `POST` | `/analyze/by-handle/summarize` | **3** — сводка по ссылке/username без id в каталоге |
| `POST` | `/analyze/{channel_id}` | **2** — `ChannelAnalysisPipeline`, запись в `analyses` |
| `POST` | `/analyze/by-handle` | **2** — анализ по `@name` / `t.me/...` через Telethon |
| `GET` | `/analyses` | Список отчётов; `?channel_id=&limit=` |
| `GET` | `/analyses/{analysis_id}` | Детальный сохранённый отчёт |
| `GET` | `/analyses/{analysis_id}/pdf` | PDF отчёта анализа (генерация on-the-fly, `Content-Disposition: inline`, без файлового кеша) |
| `DELETE` | `/analyses/{analysis_id}` | Удаление записи из `analyses` |
| `POST` | `/semantic-search` | **4** — семантика в Qdrant (`telegram_post_summaries` и `telegram_channel_windows`) после сценария 3 |
| `GET` | `/recommendations/{channel_id}` | **6** — похожие каналы (Qdrant: сводки, окна и `telegram_channel_profiles`, fallback по каталогу) |
| `POST` | `/channels/compare` | **5** — **2 или 3** канала (см. `CompareChannelsRequest.max_length`) |
| `GET` | `/export?format=json` или `format=csv` | **7** — выгрузка каналов из БД |
| `GET` | `/data-showcase`, `/data-showcase/export` | Витрина normalized records (не номерной сценарий из текстового регламента, но смежное API) |
| `GET` | `/manual-review`, `/manual-review/export` | Журнал режима **manual_review** (**8**) |
| `GET` | `/health` | Проверка работоспособности API |
| `GET`/`POST`/`DELETE` | `/channels`, `/channels/{channel_id}`, `/channels/{channel_id}/collect` | MVP каталога: список, создание, удаление канала из каталога, фон **`collect`** (см. OpenAPI summary) |
| `GET` | `/publishing/image-options` | Размер/качество для UI |
| `GET` | `/publishing/channels` | **Публикация**: каналы, куда user session может постить |
| `GET` | `/publishing/author-style` | Образцы стиля автора для LLM |
| `POST` | `/publishing/generate` | Генерация текста + изображения (без Telegram) |
| `POST` | `/publishing/publish-generated` | Генерация + публикация в канал |
| `POST` | `/publishing/publish-manual` | Ручная публикация / «Опубликовать предпросмотр» |
| `POST` | `/publishing/send-message` | Сообщение в чат от user session |

Подробнее: [docs/PUBLISHING.md](docs/PUBLISHING.md).

Сводные подсказки к маршрутам для разработчиков — в docstring/OpenAPI каждого эндпоинта в каталоге [`app/api/v1/endpoints/`](app/api/v1/endpoints/).

### Различия формы поиска (`SearchChannelsRequest`)

- **`saved_catalog`**: допускает **`count=null`** (режим «показать все»), фильтры по подписчикам и **`last_post_from`/`last_post_to`**, сортировка по каталогу, приоритет совпадений по **`channels.topic_search`**.
- **`telegram_live`**: **`count`** обязателен, диапазон **`1…15`** ([`schemas/intelligence.py`](app/schemas/intelligence.py)); **`min_subscribers`**, **`max_subscribers`** и **`last_post_from`/`last_post_to`** в теле **запрещены** и приведут к ошибке валидации. Квоты и приоритеты при обработке живого поиска см. модуль **`app/orchestration/discovery_pipeline.py`** (`contacts.Search` не даёт фильтра по числу подписчиков «из коробки»).

### Обработка ошибок

Глобально: **`PipelineValidationBlockedError`** → **422**, **`PipelineError`** → **502** ([`app/api/exception_handlers.py`](app/api/exception_handlers.py)). Эндпоинты дополнительно используют **`HTTPException`** (в т.ч. 404, 422, 503 и др.) там, где задан контракт.

### Тесты

Из каталога **`backend/`** (см. [`pyproject.toml`](pyproject.toml): `testpaths = ["tests"]`, `pytest-asyncio` в режиме **`auto`**):

```bash
pytest -q
```

Прицельный прогон маршрутов intelligence с подменёнными **`get_intelligence_service`** / **`get_vector_service`**: **`tests/test_api_v1_intelligence.py`**.

Разработческие утилиты: **`ruff`**, **`mypy`** (см. секции **`[tool.ruff]`** и **`[tool.mypy]`** в **`pyproject.toml`**).
