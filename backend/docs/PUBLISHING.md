# Публикация в Telegram (модуль «Публикация»)

Документ описывает модуль генерации постов через **OpenAI** и публикации через **Telethon user session** (не Bot API). UI: меню **«Публикация»** → `/publishing` (Next.js).

## Содержание

1. [Назначение](#назначение)
2. [Архитектура backend](#архитектура-backend)
3. [Сценарии в UI](#сценарии-в-ui)
4. [Алгоритм AI-поста](#алгоритм-ai-поста)
5. [REST API](#rest-api)
6. [Telethon](#telethon)
7. [Переменные окружения](#переменные-окружения)
8. [Стиль автора](#стиль-автора)
9. [Тесты](#тесты)

## Назначение

Модуль позволяет пользователю с **авторизованной Telethon-сессией**:

1. **Публиковать посты в свои каналы** — текст, изображение или оба (от имени user session).
2. **Писать сообщения в чаты** — личные сообщения / группы от своего имени.
3. **Генерировать посты через LLM** — текст в стиле автора + иллюстрация или инфографика (OpenAI Chat + OpenAI Images), с предпросмотром и правкой перед публикацией.

Данные **не сохраняются** в SQLite как отдельная сущность: публикация идёт напрямую в Telegram; генерация использует только in-memory / ответ API.

## Архитектура backend

```
app/publishing/
├── __init__.py          # экспорт PublishingService
├── service.py           # оркестрация: generate, publish, list channels
├── generator.py         # PostContentGenerator (OpenAI chat + images)
├── image_api.py         # маппинг size/quality под dall-e-3 vs gpt-image-*
├── web_research.py      # Responses API + web_search_preview
├── style.py             # загрузка образцов стиля автора
├── schemas.py           # PostDraftLLM, GeneratedPostContent (internal)
└── data/
    └── author_style_samples.txt   # bundled fallback

app/schemas/publishing.py        # Pydantic для REST
app/api/v1/endpoints/publishing.py
app/ai/prompts/publishing/post_draft.j2
app/ai/prompts/publishing/image_prompt_from_hint.j2

app/integrations/telethon/
├── media_bytes.py       # BytesIO + MIME → фото в ленте, не «файл»
└── user_session_service.py  # list_publishable_channels, publish_to_channel, send_user_message
```

Зависимости эндпоинтов: **`TelethonUserSessionServiceDep`** (503 без сессии), **`OPENAI_API_KEY`** для генерации (503/422).

## Сценарии в UI

### Вкладка «AI-пост в канал»

| Кнопка | Поведение |
|--------|-----------|
| **Предпросмотр** | `POST /publishing/generate` → редактор: правка **текста**, **замена/удаление** картинки → **«Опубликовать предпросмотр»** (`POST /publishing/publish-manual` с отредактированным телом). |
| **Сгенерировать и опубликовать** | `POST /publishing/publish-generated` — без редактора; вверху экрана блок **«Опубликовано»** (id сообщения, канал, тема). |

**Формат поста:**

- `post_with_image` — в канал уходит **картинка + текст** (подпись к фото).
- `infographic_only` — в канал только **изображение**; текст в UI показывается как черновик смысла (в Telegram не публикуется).

Список каналов: `GET /publishing/channels`. Опции размера/качества картинки для текущей `OPENAI_IMAGE_MODEL`: `GET /publishing/image-options`.

На вкладке AI-пост в UI:

- **Размер** и **качество** изображения (списки зависят от модели: gpt-image — `1024x1024` / `1536×1024` / `1024×1536` и `low`…`auto`; DALL·E 3 — свои значения; по умолчанию из `.env`).
- **Промпт для изображения** — если заполнен, второй structured-вызов (`ImagePromptFromHintLLM`: `image_generation_prompt` + `labels_on_image_ru`) формирует промпт с **кириллическими надписями дословно**, если редактор их просит; иначе — промпты из первого вызова.
- **Веб-поиск** — для AI-поста всегда `use_web_search: true` (Responses API, инструмент `web_search_preview`); факты подставляются в `post_draft.j2`.

Текстовые поля (редактор, ручная публикация, чат): кнопка **«Эмодзи»** (`emoji-picker-react`).

### Вкладка «Ручная публикация»

Готовый текст и/или файл изображения → `POST /publishing/publish-manual`.

### Вкладка «Сообщение в чат»

`@username`, id или ссылка + текст → `POST /publishing/send-message`.

## Алгоритм AI-поста

```mermaid
flowchart TD
  A[Тема + параметры] --> B{use_web_search?}
  B -->|да| C[Responses API web_search_preview]
  C --> D[OpenAI Chat structured post_draft]
  B -->|нет| D
  D --> E{custom_image_description?}
  E -->|да| F[Chat structured image_prompt_from_hint]
  E -->|нет| G[illustration / infographic prompt]
  F --> H[Images API]
  G --> H
  H --> I[Telethon фото в ленте]
```

1. Пользователь задаёт **тему**, **объём**, **размер/качество** картинки (или дефолты из `.env`), опционально **промпт для изображения**, **доп. информацию**, **формат**.
2. При **`use_web_search: true`** (по умолчанию для AI-поста) — [`web_research.py`](../app/publishing/web_research.py): OpenAI **Responses API** с `tools=[{"type": "web_search_preview"}]`, результат в шаблон `post_draft.j2`.
3. **OpenAI Chat** (`parse_structured`, `PostDraftLLM`) — текст поста и/или стандартные промпты для картинки.
4. Если задан **`custom_image_description`** — второй `parse_structured` (`ImagePromptFromHintLLM`) по [`image_prompt_from_hint.j2`](../app/ai/prompts/publishing/image_prompt_from_hint.j2).
5. **OpenAI Images** с `image_size` / `image_quality` из запроса (нормализация в [`image_api.py`](../app/publishing/image_api.py)).
6. **Telethon** — публикация как **фото в ленте** ([`media_bytes.py`](../app/integrations/telethon/media_bytes.py)).

## REST API

Префикс: **`/api/v1/publishing`**. Тег OpenAPI: **`publishing`**.

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/channels` | Каналы для публикации (admin/creator, broadcast) |
| `GET` | `/image-options` | Допустимые `sizes` / `qualities` и дефолты для `OPENAI_IMAGE_MODEL` |
| `GET` | `/author-style` | Превью загруженных образцов стиля + путь к файлу |
| `POST` | `/generate` | Генерация (текст + `image_base64`); тело см. ниже |
| `POST` | `/publish-generated` | Генерация + публикация в `channel_ref` |
| `POST` | `/publish-manual` | Публикация готовых `text` / `image_base64` (в т.ч. после правки предпросмотра) |
| `POST` | `/send-message` | Сообщение в чат от user session |

Пример генерации:

```bash
curl -sS -X POST "$BASE/api/v1/publishing/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "ИИ на рынке труда",
    "char_count": 1200,
    "extra_info": null,
    "output_mode": "post_with_image",
    "image_size": "1536x1024",
    "image_quality": "high",
    "custom_image_description": null,
    "use_web_search": true
  }'
```

Пример публикации после правки:

```bash
curl -sS -X POST "$BASE/api/v1/publishing/publish-manual" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_ref": "@my_channel",
    "text": "Текст поста…",
    "image_base64": "<base64 без data: prefix>"
  }'
```

Коды ошибок: **503** (нет OpenAI/Telethon), **422** (ошибка генерации, недоступный канал, Telethon RPC).

## Telethon

Методы в [`TelethonUserSessionService`](../app/integrations/telethon/user_session_service.py):

| Метод | Назначение |
|-------|------------|
| `list_publishable_channels()` | `GetAdminedPublicChannels` + диалоги с `post_messages` |
| `publish_to_channel(identifier, text=, image_bytes=)` | Фото с подписью / только фото / только текст |
| `send_user_message(identifier, text=)` | Личное сообщение |

Подробнее про сессию и FloodWait: [TELEGRAM_TELETHON.md](TELEGRAM_TELETHON.md).

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `OPENAI_API_KEY` | — | Обязателен для генерации |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Текст поста (structured) |
| `OPENAI_IMAGE_MODEL` | `dall-e-3` | Иллюстрация / инфографика |
| `OPENAI_IMAGE_SIZE` | `1024x1024` | См. комментарии в `.env.example` |
| `OPENAI_IMAGE_QUALITY` | `standard` | DALL·E: `standard`/`hd`; gpt-image: `low`/`medium`/`high`/`auto` |
| `PUBLISHING_STYLE_PATH` | пусто | Путь к файлу стиля; иначе `context/post_style.txt` или bundled |

Маппинг DALL·E ↔ gpt-image (размер `1792×*` → `1536×*` для gpt-image): [`image_api.py`](../app/publishing/image_api.py).

## Стиль автора

Образцы постов загружаются функцией `load_author_style_samples()` ([`style.py`](../app/publishing/style.py)):

1. `PUBLISHING_STYLE_PATH`, если задан и файл существует;
2. иначе `context/post_style.txt` в корне репозитория (удобно в dev);
3. иначе `app/publishing/data/author_style_samples.txt` (в Docker-образе API).

Промпт явно просит LLM **не копировать** образцы дословно, а переносить **манеру** (эмодзи, абзацы, вопрос к аудитории).

## Тесты

| Файл | Что проверяет |
|------|----------------|
| [`tests/test_publishing.py`](../tests/test_publishing.py) | стиль, схемы, `image_api` / Settings |
| [`tests/test_telethon_media_bytes.py`](../tests/test_telethon_media_bytes.py) | имя файла и MIME для фото |

```bash
cd backend && PYTHONPATH=. python3 -m pytest tests/test_publishing.py tests/test_telethon_media_bytes.py -q
```
