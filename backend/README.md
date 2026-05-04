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

Архитектура AI pipeline (RAG, tools, стадии, SQL/Qdrant): [docs/AI_PIPELINE_ARCHITECTURE.md](docs/AI_PIPELINE_ARCHITECTURE.md).

## REST API v1

Префикс: `/api/v1`. Интерактивная документация: после запуска сервера откройте `/docs` или `/redoc`.

| Метод | Путь | Сценарий (см. `context/user_scenario.txt`) |
|-------|------|---------------------------------------------|
| POST | `/search-channels` | 1 — поиск по каталогу в БД; 8 — `manual_review` при слишком общем запросе |
| GET | `/channel/{id}` | 2 — карточка канала |
| POST | `/channel/{id}/summarize` | 3 — сводка последних постов (LLM) |
| POST | `/analyze/{id}` | 2 — запуск `ChannelAnalysisPipeline`, запись в `analyses` |
| POST | `/semantic-search` | 4 — семантический поиск (Qdrant + эмбеддинг запроса) |
| GET | `/recommendations/{id}` | 6 — похожие каналы (профиль → поиск по постам) |
| POST | `/channels/compare` | 5 — сравнение метрик 2–5 каналов |
| GET | `/export?format=json` или `format=csv` | 7 — выгрузка каналов из БД |
| GET/POST | `/channels`, `/health` | CRUD каналов (MVP) и healthcheck |

Обработка ошибок: `HTTPException` для 404/503; глобально зарегистрированы `PipelineValidationBlockedError` → **422** и `PipelineError` → **502** (`app/api/exception_handlers.py`).

### Тесты API

Файл `tests/test_api_v1_intelligence.py`: проверки маршрутов с **подменой зависимостей** (`get_intelligence_service`, `get_vector_service`), чтобы не требовать живые Qdrant/OpenAI. Запуск только этого файла:

```bash
pytest tests/test_api_v1_intelligence.py -q
```
