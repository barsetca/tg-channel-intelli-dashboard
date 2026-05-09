# Telegram (Telethon): пользовательская сессия

Документация по асинхронному сервисному слою **`TelethonUserSessionService`** (`app.integrations.telethon`). Слой рассчитан на **`user session`** (MTProto пользователя), не на Bot API.

## Содержание

1. [Назначение и границы](#назначение-и-границы)
2. [Конфигурация окружения](#конфигурация-окружения)
3. [Первичная авторизация](#первичная-авторизация)
4. [Интеграция с FastAPI](#интеграция-с-fastapi)
5. [Перед RPC: сессия, FloodWait, recovery](#перед-rpc-сессия-floodwait-recovery)
6. [Публичный API класса сервиса](#публичный-api-класса-сервиса)
7. [Ошибки и лимиты (FloodWait)](#ошибки-и-лимиты-floodwait)
8. [Структура пакета](#структура-пакета)
9. [Тестирование](#тестирование)

## Назначение и границы

- **Подключение через user session** — приоритет **StringSession** (см. [`effective_string_session`](../app/integrations/telethon/session_source.py)):
  1. **`TELEGRAM_SESSION`** из `os.environ` (актуально при ротации без перечитывания кэша `get_settings()`);
  2. поле **`Settings.telegram_session`** (в `.env` / env задаётся тем же ключом **`TELEGRAM_SESSION`**, см. [`config.py`](../app/core/config.py));
  3. sidecar-файл **`{TELEGRAM_SESSION_NAME}.session.string`** в **`TELEGRAM_SESSION_DIR`** (пишется после успешного входа через **`/api/v1/telegram/auth/*`**);
  4. если строка ниоткуда не взята — SQLite-файл сессии Telethon **`{TELEGRAM_SESSION_NAME}`** (без суффикса в имени параметра клиента — Telethon добавит `.session`) в **`TELEGRAM_SESSION_DIR`**.
- **Поиск публичных каналов** через `contacts.Search` с возможностью скрыть мегагруппы (`broadcast_only=True` по умолчанию).
- **Метаданные канала** через `channels.getFullChannel` (после `get_input_entity` из сущности `Channel`).
- **Последние N постов** через `client.get_messages` с сортировкой по дате (старые первыми) и фильтром сервисных сообщений (поле `action`).
- **Интерактивный первый вход** (телефон → код → опционально 2FA) реализован **в приложении**: [`telegram_auth.py`](../app/api/v1/endpoints/telegram_auth.py) + [`TelegramInteractiveAuthFlows`](../app/integrations/telethon/interactive_auth.py). Выключается **`TELEGRAM_INTERACTIVE_LOGIN=false`** (в production часто так: только заранее выданная сессия и доверенный периметр).
- Если при старте нет авторизованной сессии, **`startup_for_fastapi()`** возвращает `(False, …)` и **`app.state.telegram_service`** остаётся **`None`** — приложение не падает. Зависимость **`TelethonUserSessionServiceDep`** для маршрутов в этом случае даёт **HTTP 503**.
- Совместный результат первого успешного входа по HTTP: строка **`telegram_session`** в ответе, запись **`TELEGRAM_SESSION`** в окружение процесса, sidecar **`*.session.string`**, удаление старых файлов **`*.session`**, пересоздание **`TelethonUserSessionService`** и обновление **`app.state.telegram_service`** (см. **`apply_new_session_and_reconnect_telegram_service`** в `interactive_auth.py`).

## Конфигурация окружения

Получите `api_id` и `api_hash` на https://my.telegram.org (раздел **API development tools**).

| Переменная | Описание |
|------------|-----------|
| `TELEGRAM_API_ID` | Числовой идентификатор приложения |
| `TELEGRAM_API_HASH` | Строка hash |
| `TELEGRAM_SESSION` | Строка **StringSession** (ручной экспорт или поле **`telegram_session`** в JSON-ответах **`POST …/telegram/auth/code`** и **`POST …/telegram/auth/password`**). Если строка есть из env (**`TELEGRAM_SESSION`** попадает в **`Settings.telegram_session`** при загрузке настроек), из sidecar (**`*.session.string`**) или из ответа, клиент собирается на **StringSession**; иначе — SQLite-файл в **`TELEGRAM_SESSION_DIR`**. Для горячего обновления без рестарта смотрится прежде всего **`os.environ`** (см. **`read_telegram_session_from_os_environ`** в `session_source.py`). |
| `TELEGRAM_INTERACTIVE_LOGIN` | `true` / `false` — разрешить HTTP-шаги первого входа (по умолчанию `true` в dev; в production часто `false`). |
| `TELEGRAM_SESSION_NAME` | Базовое имя файла сессии (Telethon добавит `.session`), когда `TELEGRAM_SESSION` пуст |
| `TELEGRAM_SESSION_DIR` | Каталог для сессии (абсолютный путь или относительный к рабочей директории backend) |
| `TELEGRAM_FLOOD_MAX_WAIT_SECONDS` | Верхний предел секунд ожидания **за один** FloodWait (актуально ограничивать мног часовые задержки) |
| `TELEGRAM_FLOOD_RETRY_ATTEMPTS` | Количество **дополнительных** попыток после первой ошибки (итого попыток = `1 + N`) |

Пример см. в корневом `.env.example`.

## Первичная авторизация

Варианты:

**A. Через API приложения** (если **`TELEGRAM_INTERACTIVE_LOGIN=true`**): последовательно **`POST /api/v1/telegram/auth/start`** (тело с телефоном в формате `+…`) → **`POST /api/v1/telegram/auth/code`** (`flow_id` + код); при ответе **`status=needs_password`** — **`POST /api/v1/telegram/auth/password`**. TTL потока — **600** с (`FLOW_TTL_SEC` в коде).

**B. Локально скриптом Telethon**: `TelegramClient.start()` и интерактивный код/2FA → в **`TELEGRAM_SESSION_DIR`** появляется файл **`{TELEGRAM_SESSION_NAME}.session`**.

**C. Секреты / CI**: экспортировать **StringSession** в **`TELEGRAM_SESSION`** или положить sidecar **`*.session.string`** / файл **`.session`**.

Контейнер в production обычно **не** ждёт stdin: используют заранее выданную сессию (**volume/secrets manager**).

## Интеграция с FastAPI

В **`app.main.lifespan`** создаются **`OrchestrationCoordinator`**, **`TelegramInteractiveAuthFlows`** (`app.state.telegram_auth_flows`), **`TelethonUserSessionService(settings)`** и **`startup_for_fastapi()`**:

- При успешном **`connect()`**: **`app.state.telegram_service`** указывает на сервис, **`telegram_startup_failure`** обнуляется.
- Если нет `api_id`/`api_hash` или сессия не авторизована: **`app.state.telegram_service == None`**, **`telegram_startup_failure`** — краткая причина для UI.

При остановке: **`telegram_service.disconnect()`**, **`telegram_auth_flows.dispose_all()`**.

Эндпоинты авторизации монтируются с префиксом **`/telegram`** относительно **`/api/v1`** ([`router.py`](../app/api/v1/router.py)):

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/v1/telegram/status` | Для фронта: `api_configured`, `session_ready`, флаги интерактивного входа, `startup_failure` |
| `POST` | `/api/v1/telegram/auth/start` | Отправить код, вернуть `flow_id` |
| `POST` | `/api/v1/telegram/auth/code` | Подтвердить код или получить `needs_password` |
| `POST` | `/api/v1/telegram/auth/password` | Пароль 2FA |

Для доменных маршрутов, которым нужен уже поднятый Telegram, используйте зависимость **`TelethonUserSessionServiceDep`** из **`app.api.deps`** (`get_telethon_user_session_service_dep`):

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

## Перед RPC: сессия, FloodWait, recovery

Публичные методы сервиса ходят в Telegram через **`_guarded_call`**: перед операцией вызывается **`ensure_session_for_api()`**, затем **`run_with_optional_flood_retry`** ([`rate_limit.py`](../app/integrations/telethon/rate_limit.py)) с параметрами из **`telegram_flood_retry_attempts`** и **`telegram_flood_max_wait_seconds`**.

Поведение **`ensure_session_for_api()`**:

- клиент поднимается **`connect()`** при отсутствии подключения или авторизации;
- если задан **StringSession** из env/settings/sidecar, а сейчас открыта **файловая** сессия — переподключение с приоритетом строки;
- если уже используется StringSession и **строка в env изменилась** по снимку `_last_string_snapshot` — клиент пересоздаётся.

Если после FloodWait-слоёв ловится одна из **восстановимых** ошибок сессии (**`AuthKeyUnregisteredError`**, **`AuthKeyInvalidError`**, **`AuthKeyDuplicatedError`**, **`SessionExpiredError`**, **`SessionRevokedError`**, **`UserDeactivatedError`**, **`UserDeactivatedBanError`** — см. **`_RECOVERABLE_SESSION_ERRORS`** в [`user_session_service.py`](../app/integrations/telethon/user_session_service.py)): выполняется **`_recover_invalid_session()`** (сброс клиента; для файловой сессии — удаление **`*.session`** и **`-journal`** через **`unlink_telethon_sqlite_session_files`**), затем снова **`ensure_session_for_api()`** и **одна** полная попытка цепочки с теми же лимитами FloodWait.

Для **`resolve_channel` / `get_entity`** лимиты FloodWait в коде ужаты (**`max_additional_attempts=0`**, малый **`cap_sleep_seconds`**) — быстрый отказ вместо долгих ожиданий на частом пути.

## Публичный API класса сервиса

| Метод | Назначение |
|-------|-------------|
| `is_configured()` | Есть ли `api_id` / `api_hash` в настройках |
| `connected` | Подключён ли сокет клиента |
| `connect()` / `disconnect()` | Явное управление клиентом |
| `ensure_session_for_api()` | Перед Telegram RPC: подключение / смена ``TELEGRAM_SESSION`` / готовность клиента |
| `startup_for_fastapi()` | Мягкий старт без исключений наружу (лог + кортеж ``(ok, reason)``) |
| `search_public_channels(query, limit=15, broadcast_only=True)` | Поиск, DTO **`TelegramSearchHit`** |
| `resolve_channel(identifier)` | Строка (`@username`, `t.me/...`) или числовой peer → **`Channel`** |
| `get_channel_info(identifier)` | **`TelegramChannelFullInfo`** (about, participants_count при наличии) |
| `fetch_recent_posts(identifier, limit=25, max_additional_fetch_rounds_for_flood=0)` | Список **`TelegramPostBrief`**, порядок **хронологический** (старые первыми); служебные сообщения с **`action`** отфильтрованы |

DTO описаны в [`dto.py`](../app/integrations/telethon/dto.py).

## Ошибки и лимиты (FloodWait)

Иерархия в [`exceptions.py`](../app/integrations/telethon/exceptions.py):

- **`TelegramConfigurationError`** — нет ключей Telegram.
- **`TelegramAuthRequiredError`** — клиент не прошёл **`is_user_authorized()`** после **`connect()`** (нужна валидная сессия или поток **`/telegram/auth/*`**).
- **`TelegramNotAuthorizedError`** — общий случай «сессии нет / ключ не принят», зарезервирован в **`exceptions.py`** и экспорт пакета; в пользовательских путях чаще встречается **`TelegramAuthRequiredError`** после **`connect()`**.
- **`TelegramRateLimitedError`** — после маппинга FloodWait/FloodTest; поле **`retry_after_seconds`**.
- **`TelegramUsernameNotFoundError`**, **`TelegramPrivateChannelError`**, **`TelegramInvalidIdentifierError`** — доменные случаи.
- **`TelegramTelethonError`** — базовый класс и обёртка для неизвестных RPC (`coerce_to_telegram_error`).

Поведение FloodWait централизовано в **`run_with_optional_flood_retry`** ([`rate_limit.py`](../app/integrations/telethon/rate_limit.py)): пауза `min(requested_seconds, cap_sleep_seconds)` и повторы до **`1 + max_additional_attempts`**; если лимит исчерпан — **`TelegramTelethonError`** («Исчерпаны попытки после FloodWait…»).

## Структура пакета

```
app/integrations/telethon/
├── __init__.py              # экспорт публичного API и DTO/исключений
├── dto.py                   # TelegramSearchHit, TelegramChannelFullInfo, TelegramPostBrief
├── exceptions.py            # иерархия ошибок, map_telethon_error / coerce_to_telegram_error
├── rate_limit.py            # run_with_optional_flood_retry (FloodWait с капом)
├── session_source.py        # effective_string_session, sidecar *.session.string, удаление *.session
├── interactive_auth.py      # TelegramInteractiveAuthFlows, реконнект после входа по HTTP
└── user_session_service.py  # TelethonUserSessionService
```

Отдельно в [`app/integrations/telethon_client.py`](../app/integrations/telethon_client.py) остаётся заготовка **`TelethonFactory`** (синхронная фабрика клиента без user-session-слоя); **боевое приложение** использует **`TelethonUserSessionService`** из пакета выше.

## Тестирование

Из каталога `backend/` после установки dev-зависимостей:

```bash
pip install -e ".[dev]"
pytest -q
```

Тесты используют `pytest-asyncio` (режим `auto` задан в `pyproject.toml`) и изолируют реальный Telegram через моки.
