# Метрики Telegram-канала (движок расчёта)

Документ описывает **что** считает модуль `app.services.channel_metrics`, **из каких входных полей** и какие переменные используются в формулах. Это должно совпадать с реализацией в:

- `[compute.py](../app/services/channel_metrics/compute.py)` — расчёт;
- `[types.py](../app/services/channel_metrics/types.py)` — `PostMetricRow`, `MetricWeights`, `ChannelMetricsSnapshot`, `ChannelMetricContext`;
- `[adapters.py](../app/services/channel_metrics/adapters.py)` — маппинг ORM (`Post`, `Channel`) → типы метрик.

Публичный импорт (реэкспорт из пакета): `from app.services.channel_metrics import compute_channel_metrics, PostMetricRow`.

---

## 1. Входные данные

### 1.1. Одна запись поста: `PostMetricRow`

| Поле        | Тип              | Смысл |
| ----------- | ---------------- | ----- |
| `posted_at` | `datetime`       | Время публикации. Если **нет** timezone, в расчётах дата считается **UTC** (`_ensure_aware_utc`). Используется для интервалов и свежести. |
| `views`     | `int \| None`    | Просмотры поста (**v**, `views`). Пост участвует в **avg_views**, **engagement_proxy** и интервалах **только** если `views is not None` и `views > 0`. |
| `forwards`  | `int \| None`    | Пересылки (**f**). `None` → при расчёте отношения берётся **0**; отрицательные значения усекаются через `max(int(forwards), 0)`. |

Связь с ORM: `Post.posted_at`, `Post.views_count`, `Post.forwards_count` → см. `post_row_from_orm()` в `adapters.py`.

### 1.2. Контекст канала: `ChannelMetricContext`

| Поле               | Смысл |
| ------------------ | ----- |
| `subscriber_count` | Подписчики канала. **В формулах не используется**; попадает в `ChannelMetricsSnapshot.meta["subscriber_count"]`. |
| `now_utc`          | Референс «сейчас» UTC для компонента свежести в **activity_score** (см. раздел 7). |

### 1.3. Настройки весов: `MetricWeights`

Все поля необязательны; при вызове функций без аргумента создаётся `MetricWeights()` с константами ниже.

| Поле                           | По умолчанию | Роль |
| ------------------------------ | ------------ | ------ |
| `min_span_weeks`               | `1e-6`       | Минимальная длина окна (**недели**) между первым и последним постом при расчёте `posting_frequency` — защита от деления на ноль. Обозначение: ε. |
| `posting_frequency_ref_per_week` | `14.0`   | Опорная частота **постов/нед**; при равной фактической частоте нормализованная частота в activity = 1.0 (перед ограничением сверху). |
| `activity_w_frequency`         | `0.55`       | Вес компоненты «частота». |
| `activity_w_recency`           | `0.35`       | Вес компоненты «свежесть». |
| `activity_w_volume`            | `0.10`       | Вес компоненты «объём выборки». |
| **Инвариант**                  | —            | Сумма `activity_w_frequency + activity_w_recency + activity_w_volume` **должна быть 1.0** (иначе при создании объекта будет `ValueError`). |
| `volume_ref_posts`             | `100.0`      | \(N_{\text{ref}}\): при \(N\) постах объём \(\ln(1+N)/\ln(1+N_{\text{ref}})\); при \(N=N_{\text{ref}}\) объёмное слагаемое = 1.0. |
| `consistency_cv_scale`         | `2.0`        | Параметр **s** в `consistency_score = 100 · exp(-CV/s)` — больше значение ⇒ мягче штраф за неравномерные интервалы. |
| `engagement_forward_rate_cap` | `1.0`        | Верхняя граница **отношения** `forwards/views` на один пост перед усреднением. |

---

## 2. Средние просмотры: `avg_views`

**Идея:** типичный охват только по постам с известными положительными просмотрами.

**Множество:** \(S = \{ i \mid views_i \neq \texttt{None} \land views_i > 0 \}\).

**Результат:** если \(S\) пусто → **`None`**. Иначе

\[
\texttt{avg\_views} = \frac{1}{|S|} \sum_{i \in S} views_i
\]

Функция: `compute_avg_views`.

---

## 3. Частота публикаций: `posting_frequency` (постов в неделю)

**Идея:** по времени между **первым** и **последним** постом (после сортировки по `posted_at`) оценить эквивалентную плотность «постов в неделю».

Обозначения:

- \(N\) — число постов (`len(posts)`).
- Посты сортируются по возрастанию времени (`_sorted_posts`).
- \(\Delta t\) — модуль разницы между временем последнего и первого поста в **часах**.
- \(\text{span\_weeks} = \max(\Delta t / 168,\ \varepsilon)\), где 168 часов = одна неделя, \(\varepsilon\) = `min_span_weeks`.

При **\(N \ge 2\)**:

\[
\texttt{posting\_frequency} = \frac{7 \cdot (N - 1)}{\text{span\_weeks}}
\]

При **\(N < 2\)** интервал между крайними постами как «окно из одной точки» не даёт устойчивой скорости → **`None`**.

Функция: `compute_posting_frequency`.

---

## 4. Прокси вовлечённости: `engagement_proxy`

**Идея:** среднее отношение пересылок к просмотрам по постам, где есть просмотры (с урогом сверху на пост).

Для каждого поста с `views > 0` и не `None`:

- \(f_i = \max(\texttt{forwards приведённое к int},\, 0)\) (при `forwards=None` используется 0 перед приведением);
- \(\texttt{cap} =\) `engagement_forward_rate_cap`;
- \(r_i = \min(f_i / v_i,\ \texttt{cap})\).

Если таких постов нет → **`0.0`**. Иначе

\[
\texttt{engagement\_proxy} = \frac{1}{|R|} \sum_{i \in R} r_i
\]

\(r_i \in [0,\ \texttt{cap}]\); при cap = 1 — типичное «mean forward rate capped at 100%».

Функция: `compute_engagement_proxy`.

---

## 5. Оценка активности: `activity_score` [0 … 100]

**Идея:** комбинация нормализованной частоты, свежести последнего поста и логарифмического «объёма» выборки.

При **\(N = 0\)** постов → **`0.0`**.

Иначе пусть:

- \(\texttt{freq} =\) результат `compute_posting_frequency` (может быть `None`);
- \(\texttt{freq\_norm} = 0\) если `freq is None`, иначе `\min(freq / F_{\text{ref}}, 1)`, где \(F_{\text{ref}}\) = `posting_frequency_ref_per_week`;
- \(\texttt{rec} =\) `_recency_component(последний posted_at, now_utc)` \(\in [0,1]\);
- \(\texttt{vol} = \ln(1+N) / \ln(1+N_{\text{ref}})\), \(N_{\text{ref}}\) = `volume_ref_posts` (если \(N\le 0\), объём принудительно 0 только в общем случае не возникает, т.к. при \(N\ge 1\) уже вошли в ветку);
- \(w_f, w_r, w_v\) — веса `activity_w_frequency`, `activity_w_recency`, `activity_w_volume`.

Сырые сумма \( \texttt{raw} = w_f \cdot \texttt{freq\_norm} + w_r \cdot \texttt{rec} + w_v \cdot \texttt{vol} \).

**Итог:**

\[
\texttt{activity\_score} = \mathrm{clamp}\bigl(100 \cdot \texttt{raw},\, 0,\, 100\bigr)
\]

(в коде — `max(0, min(100, …))`)

### Свежесть `_recency_component`

Пусть `hours` — неотрицательное число часов от времени **последнего** поста до `now_utc` (разница усекается снизу нулём: `hours = max(0, ...)`).

По **`compute.py`**:

- если `hours ≤ 72` → \(\texttt{rec} = 1.0\);
- если \(72 < \texttt{hours} \le 14\cdot 24\) — линейный спуск от **1.0** до **0.25**;
- иначе → \(\texttt{rec} = \max(0.05,\ \exp(-(\texttt{hours} - 14\cdot 24)/(30\cdot 24)))\).

Функция: `compute_activity_score`; требует явный **`now_utc`** на входе функции отдельно (при сборке снимка см. §7).

---

## 6. Регулярность графика: `consistency_score` [0 … 100]

**Идея:** чем ближе друг к другу **часы между соседними постами**, тем выше балл (`CV = pstdev(gaps)/mean(gaps)` в часах).

- **\(N < 2\)**: интервалов нет → **`50.0`** (нейтрально).
- **Ровно один интервал** (\(N=2\)): **`100.0`** (не с чем сравнивать вариативность).
- Иначе: gaps в часах между соседними постами, \(\mu = \mathrm{mean}(\texttt{gaps})\), если \(\mu \le 0\) → **`50.0`**. Стандартное отклонение — `statistics.pstdev`. \(CV=\sigma/\mu\).

\[
\texttt{consistency\_score} = 100 \cdot \exp(-CV/s), \quad s = \texttt{consistency\_cv\_scale}
\]

Функция: `compute_consistency_score`.

---

## 7. Сводный объект: `compute_channel_metrics`

Функция `compute_channel_metrics(posts, *, context=None, weights=None, now_utc=None)` возвращает **`ChannelMetricsSnapshot`**:

| Поле                 | Значение |
| -------------------- | -------- |
| `avg_views`          | `compute_avg_views` |
| `posting_frequency`  | `compute_posting_frequency` |
| `engagement_proxy`   | `compute_engagement_proxy` |
| `activity_score`     | `compute_activity_score` с временем ниже |
| `consistency_score`  | `compute_consistency_score` |
| `posts_used`         | `len(posts)` |
| `meta["now_utc_used"]` | ISO `resolved_now` |
| `meta["subscriber_count"]` | из `context` |

**Выбор референсного времени для activity:**

```
resolved_now = now_utc  (явный аргумент)
               or context.now_utc
               or datetime.now(timezone.utc)
```

Если нужна воспроизводимость (тесты, отладка), задавайте `now_utc` явно.

---

## 8. Связанные утилиты

- Отдельные функции экспортируются из `compute`: `compute_avg_views`, `compute_posting_frequency`, `compute_engagement_proxy`, `compute_activity_score`, `compute_consistency_score` — см. их использование в `app/ai/stages/context_builder.py` для краткого снимка по постам.

---

## 9. Расширение

- Передавайте свой `MetricWeights`, чтобы менять пороги без правки формул.
- При изменении набора метрик расширяйте `ChannelMetricsSnapshot` и при необходимости миграции для полей БД (`snapshots.metrics_json` и т.п.) — отдельно от этого модуля.

---

## 10. Метрики отчёта «Анализ канала» (сценарий 2, UI/PDF)

Для **пользовательского отчёта** после `POST /analyze/*` используется отдельный модуль  
[`app/services/channel_report_metrics.py`](../app/services/channel_report_metrics.py) — **не** путать с `posting_frequency` из раздела 3 (сравнение каналов, activity_score, discovery).

| Поле в UI / PDF | Как считается |
| --------------- | ------------- |
| **Канал создан** | Самая **ранняя** дата из `Channel.date` (Telethon) и самого раннего поста в выборке (`resolve_channel_created_at`). Если `Channel.date` новее реальной ленты (дата вступления сессии), берётся дата поста. |
| **Возраст канала** | Календарная разница от даты старта до «сейчас» (годы / месяцы / дни, русские склонения). |
| **Всего постов** | Релевантные посты (непустой текст, без служебных «joined the channel») с `posted_at` **от даты создания до момента запроса** в пределах загруженной истории (Telethon до 5000 + SQLite). |
| **Постов за 30 дней** | Релевантные посты с `posted_at` за последние 30 суток. |
| **Частота публикаций (метрика)** | \(\texttt{всего\_релевантных} / (\text{возраст\_канала\_в\_днях} / 7)\). Минимум 1 сутки в знаменателе, чтобы не делить на ноль. **Не** применяется нижний порог «0,05 недели» по размаху последних постов (источник завышения вроде 200 пост/нед). |
| **`channels.posts_per_week_estimate`** | При анализе пересчитывается той же формулой и сохраняется в БД для карточек/сравнения. |

Снимок метрик для повторного открытия отчёта: `analyses.result_json.channel_report_metrics`.

---

## 11. Связь с тестами

Юнит-тесты движка сравнения: [`backend/tests/test_channel_metrics_compute.py`](../tests/test_channel_metrics_compute.py).

Метрики отчёта сценария 2: [`backend/tests/test_channel_report_metrics.py`](../tests/test_channel_report_metrics.py).

Запуск и общее описание тестового контура см. в **[Тесты (backend) в корневом README](../../README.md#backend-tests)**.
