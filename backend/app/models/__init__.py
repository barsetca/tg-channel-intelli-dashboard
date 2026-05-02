"""
Пакет ORM-моделей SQLite (слой данных дашборда).

Импортируйте сущность из подмодуля или перечислите здесь для Alembic / metadata.
Соответствие пользовательским сценариям см. context/user_scenario.txt и README раздел про схему.
"""

from app.core.database import Base
from app.models.analysis import Analysis
from app.models.audit_run import AuditRun
from app.models.audit_run_item import AuditRunItem
from app.models.base import TimestampMixin
from app.models.channel import Channel
from app.models.embedding_metadata import EmbeddingMetadata
from app.models.export_job import ExportJob
from app.models.post import Post
from app.models.recommendation import Recommendation
from app.models.search_run import SearchRun
from app.models.snapshot import Snapshot

__all__ = [
    "Base",
    "TimestampMixin",
    "Analysis",
    "AuditRun",
    "AuditRunItem",
    "Channel",
    "EmbeddingMetadata",
    "ExportJob",
    "Post",
    "Recommendation",
    "SearchRun",
    "Snapshot",
]
