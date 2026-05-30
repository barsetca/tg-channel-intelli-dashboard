"""Метрики отчёта по каналу (частота, возраст, счётчики постов) — без привязки к ORM."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, Sequence

from app.datetime_compat import ensure_utc_aware


class PostLike(Protocol):
    posted_at: datetime
    text: str | None


def channel_public_url(*, username: str | None, invite_slug: str | None = None) -> str | None:
    u = (username or "").strip().lstrip("@")
    if u:
        return f"https://t.me/{u}"
    slug = (invite_slug or "").strip()
    if slug.startswith("https://t.me/"):
        return slug.split("?")[0].rstrip("/")
    if slug.startswith("t.me/"):
        return f"https://{slug.split('?')[0].rstrip('/')}"
    if slug.startswith("@"):
        return f"https://t.me/{slug.lstrip('@')}"
    return None


def format_date_ru(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    d = ensure_utc_aware(dt).date()
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(n) % 100
    n1 = n_abs % 10
    if 11 <= n_abs <= 14:
        return many
    if n1 == 1:
        return one
    if 2 <= n1 <= 4:
        return few
    return many


def _age_components(start: date, end: date) -> tuple[int, int, int]:
    years = end.year - start.year
    months = end.month - start.month
    days = end.day - start.day
    if days < 0:
        months -= 1
        prev_month = end.month - 1 or 12
        prev_year = end.year if end.month > 1 else end.year - 1
        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


def format_channel_age(created_at: datetime | None, *, now: datetime | None = None) -> str | None:
    if created_at is None:
        return None
    ref = ensure_utc_aware(now or datetime.now(timezone.utc))
    start = ensure_utc_aware(created_at)
    if ref.date() < start.date():
        return None
    y, m, d = _age_components(start.date(), ref.date())
    parts: list[str] = []
    if y > 0:
        parts.append(f"{y} {_ru_plural(y, 'год', 'года', 'лет')}")
    if m > 0:
        parts.append(f"{m} {_ru_plural(m, 'месяц', 'месяца', 'месяцев')}")
    if d > 0 or not parts:
        parts.append(f"{d} {_ru_plural(d, 'день', 'дня', 'дней')}")
    return " ".join(parts)


# Длинный порог — для отбора постов в LLM / нормализации (качество контента).
_MIN_LEN_SUBSTANTIVE_AI = 30

# Служебные сообщения Telegram (вступление в канал и т.п.)
_SERVICE_MESSAGE_MARKERS = (
    "joined the channel",
    "left the channel",
)

# Для LLM: дополнительные эвристики спама (не использовать в счётчиках отчёта:
# подстрока «бот» отсекает «робот», «чат-бот» и т.д.)
_AI_SPAM_MARKERS = (
    "реклама",
    "подписывайтесь",
)


def _is_service_message_text(lower: str) -> bool:
    return any(x in lower for x in _SERVICE_MESSAGE_MARKERS)


def _is_ai_spam_text(lower: str) -> bool:
    return any(x in lower for x in _AI_SPAM_MARKERS)


def is_relevant_post_text(text: str) -> bool:
    """Текст достаточно содержательный для этапов анализа с LLM (строгий порог)."""
    t = " ".join(text.split())
    if len(t) < _MIN_LEN_SUBSTANTIVE_AI:
        return False
    lower = t.lower()
    if _is_service_message_text(lower):
        return False
    return not _is_ai_spam_text(lower)


def is_metric_post_text(text: str) -> bool:
    """
    Пост учитывается в метриках отчёта (всего, за 30 дней, частота).

    Как fallback в «Резюмировать посты»: любой непустой текст, кроме служебных
    системных сообщений Telegram. Без подстрок «бот»/«реклама» — иначе IT-каналы занижаются.
    """
    t = " ".join(text.split())
    if not t:
        return False
    return not _is_service_message_text(t.lower())


def count_relevant_posts(
    posts: list[PostLike],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    since_utc = ensure_utc_aware(since) if since is not None else None
    until_utc = ensure_utc_aware(until) if until is not None else None
    n = 0
    for p in posts:
        posted = ensure_utc_aware(p.posted_at)
        if since_utc is not None and posted < since_utc:
            continue
        if until_utc is not None and posted > until_utc:
            continue
        text = " ".join((p.text or "").split())
        if text and is_metric_post_text(text):
            n += 1
    return n


def infer_channel_start_at(posts: Sequence[PostLike]) -> datetime | None:
    """Самый ранний пост в доступной выборке (любое сообщение с датой)."""
    if not posts:
        return None
    return min(ensure_utc_aware(p.posted_at) for p in posts)


def resolve_channel_created_at(
    *,
    telegram_channel_date: datetime | None = None,
    posts: Sequence[PostLike] = (),
) -> datetime | None:
    """
    Дата создания канала для отчёта: **самая ранняя** из ``Channel.date`` и дат постов в выборке.

    Если ``Channel.date`` новее реальной истории (дата вступления сессии), побеждает более ранний пост.
    """
    candidates: list[datetime] = []
    if telegram_channel_date is not None:
        candidates.append(ensure_utc_aware(telegram_channel_date))
    for infer in (infer_metric_channel_start_at, infer_channel_start_at):
        dt = infer(posts)
        if dt is not None:
            candidates.append(ensure_utc_aware(dt))
    if not candidates:
        return None
    return min(candidates)


def infer_metric_channel_start_at(posts: Sequence[PostLike]) -> datetime | None:
    """
    Дата старта для частоты публикаций: самый ранний **учтённый** пост (с непустым текстом).

    Не опирается на пустые/служебные сообщения в длинной истории — иначе возраст завышается,
    а частота (постов/нед) занижается.
    """
    dated: list[datetime] = []
    for p in posts:
        text = " ".join((p.text or "").split())
        if text and is_metric_post_text(text):
            dated.append(ensure_utc_aware(p.posted_at))
    if not dated:
        return None
    return min(dated)


def channel_age_days(
    created_at: datetime | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if created_at is None:
        return None
    ref = ensure_utc_aware(now or datetime.now(timezone.utc))
    start = ensure_utc_aware(created_at)
    days = (ref - start).total_seconds() / 86400.0
    if days < 0:
        return None
    return days


def count_relevant_posts_last_days(posts: list[PostLike], *, days: int, now: datetime | None = None) -> int:
    ref = ensure_utc_aware(now or datetime.now(timezone.utc))
    cutoff = ref - timedelta(days=days)
    n = 0
    for p in posts:
        text = " ".join((p.text or "").split())
        if not text or not is_metric_post_text(text):
            continue
        if ensure_utc_aware(p.posted_at) >= cutoff:
            n += 1
    return n


def compute_publication_frequency_per_week(
    relevant_post_count: int,
    *,
    channel_created_at: datetime | None,
    sample_posts: list[PostLike],
    now: datetime | None = None,
) -> float | None:
    """
    Постов в неделю: ``всего_релевантных_постов / (возраст_канала_в_днях / 7)``.

    Возраст считается от даты старта канала (обычно самый ранний пост в истории).
    """
    if relevant_post_count <= 0:
        return 0.0

    ref = ensure_utc_aware(now or datetime.now(timezone.utc))

    if channel_created_at is not None:
        age_days = channel_age_days(channel_created_at, now=ref)
        if age_days is None:
            return None
        # Один календарный день жизни канала — минимум сутки, чтобы не делить на ноль.
        effective_days = max(age_days, 1.0)
        weeks = effective_days / 7.0
        return float(relevant_post_count) / weeks

    dated: list[datetime] = []
    for p in sample_posts:
        text = " ".join((p.text or "").split())
        if text and is_metric_post_text(text):
            dated.append(ensure_utc_aware(p.posted_at))
    if not dated:
        return None
    if len(dated) == 1:
        return float(relevant_post_count) / 1.0

    first_dt = min(dated)
    last_dt = max(dated)
    span_days = max((last_dt - first_dt).total_seconds() / 86400.0, 1.0)
    # Запасной режим без даты старта канала: не занижать окно сильнее 1 недели.
    weeks = max(span_days / 7.0, 1.0)
    return float(relevant_post_count) / weeks


def format_publication_frequency(freq: float | None) -> str:
    if freq is None:
        return "Недостаточно данных"
    return f"{freq:.2f} поста/нед"
