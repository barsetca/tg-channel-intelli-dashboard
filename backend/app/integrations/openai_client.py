"""OpenAI embeddings and chat — thin wrapper for injection into services/pipelines."""

from openai import AsyncOpenAI

from app.core.config import settings


class OpenAIClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def embedding_model(self) -> str:
        return settings.openai_embedding_model

    @property
    def chat_model(self) -> str:
        return settings.openai_chat_model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]
