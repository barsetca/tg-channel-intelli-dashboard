# Telegram (Telethon): пользовательская сессия

Документация по асинхронному сервисному слою **`TelethonUserSessionService`** (`app.integrations.telethon`). Слой рассчитан на **`user session`** (MTProto пользователя), не на Bot API.

## Содержание

1. [Назначение и границы](#назначение-и-границы)
2. [Конфигурация окружения](#конфигурация-окружения)
3. [Первичная авторизация (получение .session)](#первичная-авторизация-получение-session)
4. [Интеграция с FastAPI](#интеграция-с-fastapi)
5. [Публичный API класса сервиса](#публичный-api-класса-сервиса)
6. [Ошибки и лимиты (FloodWait)](#ошибки-и-лимиты-floodwait)
7. [Структура пакета](#структура-пакета)
8. [Тестирование](#тестирование)

## Назначение и границы

- **Подключение через user session**: Telethon сохраняет ключи авторизации в файле `*.session` в каталоге `TELEGRAM_SESSION_DIR` (имя задаётся `TELEGRAM_SESSION_NAME`).
- **Поиск публичных каналов** через `contacts.Search` с возможностью скрыть мегагруппы (`broadcast_only=True` по умолчанию).
- **Метаданные канала** через `channels.getFullChannel` (после `get_input_entity` из сущности `Channel`).
- **Последние N постов** через `client.get_messages` с сортировкой по дате (старые первыми) и фильтром сервисных сообщений (поле `action`).
- **`TelethonUserSessionService` не выполняет интерактивный первый вход** (SMS-код и 2FA). Без готового `.session` метод `connect()` поднимает `TelegramAuthRequiredError`; HTTP-слой получает недоступный сервис через зависимость (см. ниже).

## Конфигурация окружения

Получите `api_id` и `api_hash` на https://my.telegram.org (раздел **API development tools**).

| Переменная | Описание |
|------------|-----------|
| `TELEGRAM_API_ID` | Числовой идентификатор приложения |
| `TELEGRAM_API_HASH` | Строка hash |
| `TELEGRAM_SESSION_NAME` | Базовое имя файла сессии (Telethon добавит `.session`) |
| `TELEGRAM_SESSION_DIR` | Каталог для сессии (абсолютный путь или относительный к рабочей директории backend) |
| `TELEGRAM_FLOOD_MAX_WAIT_SECONDS` | Верхний предел секунд ожидания **за один** FloodWait (актуально ограничивать мног часовые задержки) |
| `TELEGRAM_FLOOD_RETRY_ATTEMPTS` | Количество **дополнительных** попыток после первой ошибки (итого попыток = `1 + N`) |

Пример см. в корневом `.env.example`.

## Первичная авторизация (получение .session)

Разовый сценарий (локально или в безопасной среде):

1. Выставите `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_DIR`.
2. Выполните минимальный скрипт Telethon с `TelegramClient.start()` и интерактивным вводом кода/пароля 2FA.
3. Убедитесь, что в `TELEGRAM_SESSION_DIR` появился файл `имя.session`.

Производственный контейнер **не должен** ждать интерактивного stdin: туда копируют заранее созданную сессию (volume/secrets менеджер).

## Интеграция с FastAPI

В **`app.main.lifespan`** при старте создаётся `TelethonUserSessionService(settings)` и вызывается **`startup_for_fastapi()`**:

- При успешном подключении и авторизации: **`app.state.telegram_service`** указывает на экземпляр сервиса.
- Если ключей нет или сессия не авторизована: **`app.state.telegram_service == None`**; приложение стартует без падений.

При остановке вызывается **`disconnect()`**.

Для маршрутов используйте зависимость **`TelethonUserSessionServiceDep`** из `app.api.deps`:

- Если Telegram недоступен, клиент получит **HTTP 503** с пояснением (настройте мониторинг/ретраи на стороне UI).

Пример заготовки роутера:

```python
from fastapi import APIRouter

from app.api.deps import TelethonUserSessionServiceDep

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/search")
async def search_channels(q: str, telegram: TelethonUserSessionServiceDep):
    return await telegram.search_public_channels(q, limit=10)
```

## Публичный API класса сервиса

| Метод | Назначение |
|-------|-------------|
| `is_configured()` | Есть ли `api_id` / `api_hash` в настройках |
| `connected` | Подключён ли сокет клиента |
| `connect()` / `disconnect()` | Явное управление клиентом |
| `startup_for_fastapi()` | Мягкий старт без исключений наружу (лог + bool) |
| `search_public_channels(query, limit=15, broadcast_only=True)` | Поиск, DTO **`TelegramSearchHit`** |
| `resolve_channel(identifier)` | Строка (`@username`, `t.me/...`) или числовой peer → **`Channel`** |
| `get_channel_info(identifier)` | **`TelegramChannelFullInfo`** (about, participants_count при наличии) |
| `fetch_recent_posts(identifier, limit=25, …)` | Список **`TelegramPostBrief`**, порядок хронологический |

DTO описаны в `app.integrations.telethon.dto`.

## Ошибки и лимиты (FloodWait)

Иерархия в **`app.integrations.telethon.exceptions`**:

- **`TelegramConfigurationError`** — нет ключей Telegram.
- **`TelegramAuthRequiredError`** — сессия есть, пользователь не авторизован (`connect`).
- **`TelegramRateLimitedError`** — после маппинга FloodWait/FloodTest; поле **`retry_after_seconds`**.
- **`TelegramUsernameNotFoundError`**, **`TelegramPrivateChannelError`**, **`TelegramInvalidIdentifierError`** — доменные случаи.
- **`TelegramTelethonError`** — базовый класс и обёртка для неизвестных RPC (`coerce_to_telegram_error`).

Поведение FloodWait централизовано в **`run_with_optional_flood_retry`** (`rate_limit.py`): после паузы (с ограничением **`cap_sleep_seconds`**) выполняется повтор до исчерпания попыток, затем выбрасывается **`TelegramTelethonError`** с сохранением причины.

## Структура пакета

```
app/integrations/telethon/
├── __init__.py              # экспорт публичного API
├── dto.py                   # Pydantic-модели ответов
├── exceptions.py            # ошибки и map_telethon_error / coerce
├── rate_limit.py            # FloodWait с капом и ретраями
└── user_session_service.py # TelethonUserSessionService
```

## Тестирование

Из каталога `backend/` после установки dev-зависимостей:

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

Тесты используют `pytest-asyncio` (режим `auto` задан в `pyproject.toml`) и изолируют реальный Telegram через моки.
