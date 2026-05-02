"""AI pipeline contracts — extend for ingest → chunk → embed → index → retrieve → generate."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class PipelineContext:
    """Shared context for pipeline steps (DB session, trace ids, feature flags)."""

    db: AsyncSession


class EmbeddingPipeline(Protocol):
    """Example protocol: implement for batch embedding + Qdrant upsert."""

    async def run(self, ctx: PipelineContext, text_batch: list[str]) -> None: ...
