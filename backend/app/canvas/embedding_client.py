"""Embedding client for Qwen3-Embedding-8B via OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from app.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Prefix prepended to short sticky-note texts to improve embedding quality
_EMBEDDING_PREFIX = "設計思考便條紙："

# Max texts per API call
_BATCH_SIZE = 32


class EmbeddingClient:
    """Async client for computing text embeddings."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
        )
        self._model = settings.EMBEDDING_MODEL

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed a list of texts. Returns one vector per text."""
        if not texts:
            return []

        prefixed = [f"{_EMBEDDING_PREFIX}{t}" for t in texts]
        all_embeddings: list[list[float]] = []

        for start in range(0, len(prefixed), _BATCH_SIZE):
            batch = prefixed[start : start + _BATCH_SIZE]
            try:
                response = await self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                )
                # Sort by index to guarantee order
                sorted_data = sorted(response.data, key=lambda d: d.index)
                all_embeddings.extend([d.embedding for d in sorted_data])
            except Exception:
                logger.exception("Embedding API call failed for batch starting at %d", start)
                raise

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text. Convenience wrapper around embed_texts."""
        results = await self.embed_texts([text])
        return results[0]


# Module-level singleton
_instance: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    """Return the module-level EmbeddingClient singleton."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        _instance = EmbeddingClient()
    return _instance
