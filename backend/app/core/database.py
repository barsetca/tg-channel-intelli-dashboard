from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _ensure_sqlite_parent_dir(url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        path = Path(url.removeprefix(prefix))
        path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent_dir(settings.database_url)

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    """Для SQLite включаем поддержку ON DELETE / FOREIGN KEY на каждом соединении."""
    url = str(engine.url)
    if "sqlite" not in url.lower():
        return
    cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for ORM models."""


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
