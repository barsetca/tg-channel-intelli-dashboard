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
