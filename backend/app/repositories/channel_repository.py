from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import Text, asc, cast, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import expression

from app.models.channel import Channel
from app.repositories.base import BaseRepository

# Короткие служебные слова (EN): не используем как отдельные токены для OR-поиска.
_CATALOG_TOPIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)


def normalize_catalog_topic_phrase(topic: str) -> str:
    """Нижний регистр, разделители ниши (& , / …) → пробел, схлопывание пробелов."""
    s = topic.strip().lower()
    for ch in "&;,/|\\":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def catalog_search_like_fragments(topic: str) -> list[str]:
    """
    Подстроки для ILIKE OR по каталогу: исходная фраза, нормализованная фраза,
    значимые токены (длина ≥ 4) — чтобы «investing & personal finance» находило
    каналы по «finance» / «investing» без точного совпадения всей строки.
    """
    raw = topic.strip()
    norm = normalize_catalog_topic_phrase(topic)
    words = norm.split() if norm else []
    tokens: list[str] = []
    for w in words:
        w = w.strip("'\"")
        if len(w) < 2:
            continue
        if w in _CATALOG_TOPIC_STOPWORDS:
            continue
        w = w.replace("%", "").replace("_", "")
        if w:
            tokens.append(w)

    frags: list[str] = []
    seen: set[str] = set()

    def add(frag: str) -> None:
        f = frag.strip()
        if not f:
            return
        key = f.lower()
        if key in seen:
            return
        seen.add(key)
        frags.append(f)

    if raw:
        add(raw)
    if norm:
        add(norm)
    for t in tokens:
        if len(t) >= 4:
            add(t)
    return frags


def _catalog_fields_ilike(frag: str) -> expression.ColumnElement[bool]:
    safe = frag.strip().replace("%", "").replace("_", "")
    if not safe:
        return expression.false()
    pattern = f"%{safe}%"
    topics_txt = cast(Channel.topics_json, Text)
    return or_(
        Channel.topic_search.ilike(pattern),
        Channel.primary_topic.ilike(pattern),
        Channel.title.ilike(pattern),
        Channel.description.ilike(pattern),
        topics_txt.ilike(pattern),
    )


class ChannelRepository(BaseRepository[Channel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Channel)

    async def get_by_telegram_id(self, telegram_id: int) -> Channel | None:
        result = await self._session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    def _catalog_query_base(
        self,
        *,
        min_subscribers: int | None,
        max_subscribers: int | None,
        language: str | None,
        region_country: str | None,
        username_query: str | None,
        last_post_at_gte: datetime | None,
        last_post_at_lte: datetime | None,
    ):
        stmt = select(Channel)
        if min_subscribers is not None:
            stmt = stmt.where(
                Channel.subscriber_count.is_not(None)
                & (Channel.subscriber_count >= min_subscribers)
            )
        if max_subscribers is not None:
            stmt = stmt.where(
                Channel.subscriber_count.is_not(None)
                & (Channel.subscriber_count <= max_subscribers)
            )
        if language:
            stmt = stmt.where(
                or_(Channel.language_hint == language, Channel.language_hint.is_(None))
            )
        if region_country:
            stmt = stmt.where(Channel.region_country == region_country)
        if username_query:
            uname = username_query.strip().lstrip("@")
            if uname:
                stmt = stmt.where(Channel.username.ilike(f"%{uname}%"))
        if last_post_at_gte is not None:
            stmt = stmt.where(
                Channel.last_post_at.is_not(None) & (Channel.last_post_at >= last_post_at_gte)
            )
        if last_post_at_lte is not None:
            stmt = stmt.where(
                Channel.last_post_at.is_not(None) & (Channel.last_post_at <= last_post_at_lte)
            )
        return stmt

    def _catalog_ordering(
        self,
        *,
        sort_by: str,
        sort_order: str,
    ) -> tuple[expression.ColumnElement[object], ...]:
        by_subs = sort_by == "subscriber_count"
        order_desc = sort_order == "desc"
        if by_subs:
            main = (
                desc(Channel.subscriber_count).nulls_last()
                if order_desc
                else asc(Channel.subscriber_count).nulls_last()
            )
            return (main, desc(Channel.last_sync_at).nulls_last(), desc(Channel.id))
        main = (
            desc(Channel.last_sync_at).nulls_last()
            if order_desc
            else asc(Channel.last_sync_at).nulls_last()
        )
        return (main, desc(Channel.subscriber_count).nulls_last(), desc(Channel.id))

    async def search_catalog(
        self,
        *,
        topic: str,
        limit: int | None,
        min_subscribers: int | None = None,
        max_subscribers: int | None = None,
        language: str | None = None,
        region_country: str | None = None,
        new_only: bool = False,
        sort_by: str = "subscriber_count",
        sort_order: str = "desc",
        username_query: str | None = None,
        last_post_at_gte: datetime | None = None,
        last_post_at_lte: datetime | None = None,
    ) -> list[Channel]:
        """
        Поиск по локальной БД (сценарий 1, шаг «каталог»).
        Тематика — по полям title / description / primary_topic / topics_json (текстовый CAST).
        Несколько фрагментов объединяются через OR (полнота выдачи по нише).
        """
        frags = catalog_search_like_fragments(topic)
        if not frags:
            return []
        if new_only:
            sort_by = "last_sync_at"
            sort_order = "desc"
        ordering = self._catalog_ordering(sort_by=sort_by, sort_order=sort_order)
        base = self._catalog_query_base(
            min_subscribers=min_subscribers,
            max_subscribers=max_subscribers,
            language=language,
            region_country=region_country,
            username_query=username_query,
            last_post_at_gte=last_post_at_gte,
            last_post_at_lte=last_post_at_lte,
        )
        # Приоритет: сначала точечное поле topic_search, затем расширенные текстовые поля.
        primary_patterns = [
            f"%{f.strip().replace('%', '').replace('_', '')}%"
            for f in frags
            if f.strip()
        ]
        primary_match = or_(*(Channel.topic_search.ilike(p) for p in primary_patterns))
        primary_stmt = base.where(primary_match).order_by(*ordering)
        if limit is not None:
            primary_stmt = primary_stmt.limit(limit)
        primary_rows = list((await self._session.execute(primary_stmt)).scalars().all())
        if limit is not None and len(primary_rows) >= limit:
            return primary_rows[:limit]

        matched_ids = {r.id for r in primary_rows}
        secondary_match = or_(*(_catalog_fields_ilike(f) for f in frags))
        secondary_stmt = base.where(secondary_match)
        if matched_ids:
            secondary_stmt = secondary_stmt.where(Channel.id.not_in(matched_ids))
        secondary_stmt = secondary_stmt.order_by(*ordering)
        if limit is not None:
            secondary_stmt = secondary_stmt.limit(max(0, limit - len(primary_rows)))
        secondary_rows = list((await self._session.execute(secondary_stmt)).scalars().all())
        return primary_rows + secondary_rows

    async def existing_telegram_ids_among(self, telegram_ids: Sequence[int]) -> set[int]:
        """Множество telegram_id, которые уже есть в каталоге (для new_only)."""
        ids = list({int(x) for x in telegram_ids})
        if not ids:
            return set()
        result = await self._session.execute(
            select(Channel.telegram_id).where(Channel.telegram_id.in_(ids))
        )
        return {int(x) for x in result.scalars().all()}

    async def upsert_discovery_channel(
        self,
        *,
        telegram_id: int,
        username: str | None,
        title: str | None,
        description: str | None,
        subscriber_count: int | None,
        invite_slug: str | None,
        primary_topic: str | None,
        topic_search: str | None,
        language_hint: str | None,
        region_country: str | None,
    ) -> Channel:
        """Создать или обновить канал по результатам discovery (сценарий 1)."""
        existing = await self.get_by_telegram_id(telegram_id)
        if existing is not None:
            if username is not None:
                existing.username = username
            if title is not None:
                existing.title = title
            if description is not None:
                existing.description = description
            if subscriber_count is not None:
                existing.subscriber_count = subscriber_count
            if invite_slug is not None:
                existing.invite_slug = invite_slug
            if primary_topic is not None:
                existing.primary_topic = primary_topic
            if topic_search is not None:
                existing.topic_search = topic_search
            if language_hint is not None:
                existing.language_hint = language_hint
            if region_country is not None:
                existing.region_country = region_country
            existing.sync_status = "discovered"
            existing.last_sync_at = datetime.now(timezone.utc)
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        ch = Channel(
            telegram_id=telegram_id,
            username=username,
            title=title,
            description=description,
            subscriber_count=subscriber_count,
            invite_slug=invite_slug,
            primary_topic=primary_topic,
            topic_search=topic_search,
            language_hint=language_hint,
            region_country=region_country,
            sync_status="discovered",
            last_sync_at=datetime.now(timezone.utc),
            is_public_accessible=True,
        )
        return await self.add(ch)
