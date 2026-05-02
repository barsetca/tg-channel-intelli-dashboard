# Telegram Channel Intelligence Dashboard

## О продукте

Платформа для поиска, сбора, анализа и интеллектуальной обработки данных Telegram-каналов с использованием AI-пайплайна, semantic search и витрины данных.

Монорепозиторий: **FastAPI** (Python), **SQLite** + **SQLAlchemy**, **Telethon**, **OpenAI**, **Qdrant**, фронтенд на **Next.js** (TypeScript, Tailwind CSS).

---

## Требования

| Компонент | Версия / примечание |
|-----------|----------------------|
| Python | 3.10+ (в Docker используется 3.12) |
| Node.js | 20+ (для Next.js 15) |
| npm | установка фронтенда из каталога `apps/web` |
| Docker и Docker Compose | опционально, для полного стека и Qdrant |

---

## Запуск проекта на текущем этапе

На этом этапе доступны: каркас API (`/api/v1/health`, черновик работы с каналами), Next.js-интерфейс и страница проверки связи с API (`/health`). Интеграции Telethon / OpenAI / Qdrant подключены в коде как заготовки и требуют ключей в `.env` для реальной работы.

### 1. Клонирование и переменные окружения

```bash
git clone <url-репозитория>
cd tg-channel-intelli-dashboard
cp .env.example .env
```

Отредактируйте `.env` при необходимости:

- **`DATABASE_URL`** — по умолчанию SQLite в `backend/data/app.db` (относительно рабочей директории процесса backend).
- **`QDRANT_URL`** — для локального API без Docker укажите `http://localhost:6333`, если Qdrant запущен отдельно.
- **`OPENAI_API_KEY`** — см. [платформу OpenAI](https://platform.openai.com/api-keys); нужен для эмбеддингов и LLM.
- **`TELEGRAM_API_ID`**, **`TELEGRAM_API_HASH`**, **`TELEGRAM_SESSION_NAME`** — для клиента Telethon; как получить первые два поля — в следующем подразделе.
- **`NEXT_PUBLIC_API_BASE_URL`** — базовый URL API для браузера (обычно `http://localhost:8000`).
- **`API_URL`** — для серверных запросов Next.js в Docker: в `docker-compose` уже выставлен `http://api:8000`; локально без Docker можно не задавать.

#### Telegram (Telethon): `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_NAME`

Это учётные данные **пользовательского API Telegram** (MTProto), которые Telegram выдаёт для **ваших собственных приложений** (не путать с токеном [@BotFather](https://t.me/BotFather) — он нужен только для ботов).

**Как получить `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`**

1. Откройте **[my.telegram.org](https://my.telegram.org)** и войдите под своим **номером телефона**, привязанным к Telegram (придёт код в приложение Telegram).
2. Перейдите в раздел **«API development tools»** (или «Developing apps»).
3. Если приложение ещё не создано, заполните короткую форму (название приложения и т.п.) и подтвердите.
4. На странице вы увидите:
   - **`api_id`** — целое число → подставьте в **`TELEGRAM_API_ID`** в `.env`;
   - **`api_hash`** — строка из букв и цифр → в **`TELEGRAM_API_HASH`**.
5. Храните пару **api_id / api_hash** как секрет: их нельзя публиковать в репозитории и светить в скриншотах.

**`TELEGRAM_SESSION_NAME`** — базовое имя файла сессии Telethon на диске (без расширения). После первого интерактивного входа рядом появится файл вида `<имя>.session`. Задайте своё имя, если несколько окружений или аккаунтов.

Без заполненных **`TELEGRAM_API_ID`** и **`TELEGRAM_API_HASH`** фабрика клиента Telethon в проекте вернёт `None` (см. `app/integrations/telethon_client.py`), пока вы не добавите реальный код авторизации и вызовов.

#### Qdrant: `QDRANT_URL` и `QDRANT_API_KEY`

**`QDRANT_URL`** — адрес HTTP API Qdrant (порт по умолчанию **6333**). Для сервиса из `docker-compose` из контейнера API обычно указывают `http://qdrant:6333`; при запуске API на хосте и Qdrant в Docker — `http://localhost:6333`.

**`QDRANT_API_KEY`** — это **не «лицензия» и не ключ от движка векторов**, а **секрет для авторизации HTTP-запросов к Qdrant**, если на стороне сервера включена проверка API-ключа.

| Сценарий | Что делать с `QDRANT_API_KEY` |
|----------|--------------------------------|
| Локальный Qdrant из этого репозитория (`docker compose up qdrant` или полный compose) | Оставьте **пустым**: образ по умолчанию **без** обязательного ключа. |
| [Qdrant Cloud](https://cloud.qdrant.io/) или свой кластер с включённой аутентификацией | Укажите **ключ из панели / конфигурации** — тот же ключ должен быть настроен на стороне Qdrant, иначе запросы от backend будут отклоняться (`401`). |
| Продакшен за reverse proxy с проверкой заголовка | Задайте ключ и передавайте его в переменной окружения Qdrant согласно [документации Qdrant](https://qdrant.tech/documentation/guides/security/). |

В коде backend ключ передаётся клиенту только если переменная непустая (см. `app/integrations/qdrant_client.py`). Пустое значение означает «подключаться без заголовка `api-key`».

### 2. Локальный запуск только backend (API)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Файл `.env` должен лежать в **корне репозитория** или рядом с приложением — настройки читают `.env` из текущего окружения и родительских путей (см. `app/core/config.py`). Удобно скопировать `.env` в корень репозитория перед запуском.

Примените миграции и запустите сервер:

```bash
export PYTHONPATH=.
python3 -m alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка: откройте в браузере или через curl документацию OpenAPI — `http://localhost:8000/docs`, либо эндпоинт здоровья — `http://localhost:8000/api/v1/health`.

### 3. Локальный запуск только frontend (Next.js)

В отдельном терминале:

```bash
cd apps/web
npm install
```

Убедитесь, что в корне репозитория есть `.env` с **`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`** (или экспортируйте переменную перед `npm run dev`). Запуск режима разработки:

```bash
npm run dev
```

Приложение: **http://localhost:3000**. Страница проверки связи с API: **http://localhost:3000/health** (серверный запрос к backend; backend должен быть запущен).

**Примечание.** В корне объявлен npm workspace с пакетом `@tgci/web`; при старых версиях npm workspaces могут работать неполно. Надёжный способ — выполнять `npm install` и скрипты из каталога **`apps/web`**, как показано выше.

### 4. Запуск через Docker Compose (API + Qdrant + Web)

Из **корня** репозитория, где лежат `docker-compose.yml` и `.env`:

```bash
docker compose up --build
```

Поднимутся сервисы:

| Сервис | Назначение | Порт (хост) |
|--------|------------|-------------|
| `qdrant` | векторная БД | 6333 (HTTP), 6334 (gRPC) |
| `api` | FastAPI | 8000 |
| `web` | Next.js | 3000 |

База SQLite монтируется в `./backend/data`. Перед первым запуском контейнера API entrypoint выполняет **`alembic upgrade head`**.

После старта:

- фронтенд: http://localhost:3000  
- API и Swagger: http://localhost:8000/docs  
- проверка здоровья API: http://localhost:8000/api/v1/health  

Если страница `/health` во фронтенде не видит API, проверьте `.env`: для контейнера `web` заданы `API_URL=http://api:8000` и `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.

**Если `:3000` не открывается, а `:8000/docs` работает.** Чаще всего контейнер `web` упал при старте (например, не найден `server.js` в образе). Проверьте статус и логи:

```bash
docker compose ps -a
docker compose logs web
```

После правок Dockerfile или `apps/web/next.config.ts` пересоберите фронт и поднимите сервис заново:

```bash
docker compose build web --no-cache
docker compose up -d web
```

### 5. Только Qdrant локально (без полного Compose)

Если нужен только векторный сервис для разработки:

```bash
docker compose up qdrant
```

В `.env` для backend укажите `QDRANT_URL=http://localhost:6333`.

---

## Структура репозитория (кратко)

- **`backend/`** — приложение FastAPI, слои `api`, `services`, `repositories`, `models`, `schemas`, интеграции и AI-пайплайны.
- **`apps/web/`** — Next.js с Tailwind.
- **`docker-compose.yml`** — оркестрация сервисов.
- **`.env.example`** — образец переменных окружения.

Дополнительные команды только для backend см. в [backend/README.md](backend/README.md).
